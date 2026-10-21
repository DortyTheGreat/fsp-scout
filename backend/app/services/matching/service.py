"""Подбор: разбор потребности, каталог категорий, ранжированная выдача, поиск по банку, аналитика отказов."""
from __future__ import annotations

import statistics
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CandidateProfile, Consent, Invitation, Need, RankingModel, ShortlistEntry
from app.services import nlp
from app.services.llm import get_llm
from app.services.fsp import scoring as fsp_scoring
from app.services.matching import ranker
from app.taxonomy import (ADJACENT_SPECS, DECLINE_REASONS, GRADE_BY_SLUG, GRADE_ORDER, SKILL_BY_SLUG, SPEC_BY_SLUG,
                          SPECIALIZATIONS, grade_shift)

NEED_SCHEMA = {"title": "string", "specialization": "backend|frontend|data_science|devops|qa",
               "grades": ["intern|junior|middle|senior"], "must_skills": ["string"], "nice_skills": ["string"],
               "work_formats": ["office|hybrid|remote"], "city": "string|null", "salary_from": "integer|null",
               "salary_to": "integer|null"}
NEED_SYSTEM = ("Ты помогаешь работодателю формализовать потребность в ИТ-специалисте. Извлеки факты строго из "
               "текста, ничего не придумывай. specialization — одна из: backend, frontend, data_science (анализ "
               "данных, ML), devops (DevOps, SRE, инфраструктура), qa (тестирование). grades — из: intern (стажёр, "
               "без опыта), junior (до 1–2 лет), middle (2–4 года), senior (от 4 лет, ведущий, lead); если "
               "подходят несколько — перечисли все. must_skills — обязательные технологии и навыки, nice_skills — "
               "желательные («будет плюсом», nice to have); то, что явно не нужно, не включай. work_formats — из: "
               "office, hybrid, remote. salary_from и salary_to — рубли в месяц целым числом (300к → 300000), "
               "null, если не указано. city — город, если он назван.")


# ------------------------------------------------------------------ разбор потребности
def _short_title(text: str, limit: int = 80) -> str:
    first = text.strip().split("\n")[0]
    first = first.split(". ")[0].split(": ")[0].rstrip(".")
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first
def parse_need_rules(text: str) -> dict:
    skills = nlp.extract_skills(text)
    must, nice = nlp.split_must_nice(text, skills)
    grade = nlp.extract_grade(text)
    sf, st = nlp.extract_salary(text)
    return {"title": _short_title(text), "specialization": nlp.extract_specialization(text) or "backend",
            "grades": [grade] if grade else ["middle"], "must_skills": must, "nice_skills": nice,
            "work_formats": nlp.extract_formats(text), "city": nlp.extract_city(text), "salary_from": sf,
            "salary_to": st}


def need_llm_extract(text: str) -> dict | None:
    """Сырой ответ LLM; None — LLM выключена, недоступна или ответила не JSON."""
    llm = get_llm()
    if llm.name == "none":
        return None
    # работодатель ждёт ответа: короткий таймаут, при превышении — разбор правилами
    out = llm.chat_json(NEED_SYSTEM, text[:6000], NEED_SCHEMA, timeout_s=settings.llm_interactive_timeout_s)
    return out if isinstance(out, dict) else None


def _list(v) -> list:
    if isinstance(v, str):
        return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
    return list(v) if isinstance(v, (list, tuple)) else []


def _rub(v) -> int | None:
    try:
        x = int(float(str(v).replace(" ", "").replace("\u00a0", "")))
    except (TypeError, ValueError):
        return None
    if 0 < x < 1000:  # «300» в ответе модели — тысячи рублей
        x *= 1000
    return x if 10_000 <= x <= 5_000_000 else None


def need_from_llm(out: dict | None) -> dict:
    """Поля только из ответа LLM, без правил (для сравнения методов в validation/llm_compare.py)."""
    out = out or {}
    must = nlp.extract_skills(", ".join(map(str, _list(out.get("must_skills")))))
    nice = [x for x in nlp.extract_skills(", ".join(map(str, _list(out.get("nice_skills"))))) if x not in must]
    spec = out.get("specialization")
    return {"title": str(out["title"])[:120] if out.get("title") else None,
            "specialization": spec if spec in SPEC_BY_SLUG else None,
            "grades": [g for g in GRADE_ORDER if g in _list(out.get("grades"))],
            "must_skills": must, "nice_skills": nice,
            "work_formats": [x for x in ("office", "hybrid", "remote") if x in _list(out.get("work_formats"))],
            "city": str(out["city"])[:120] if isinstance(out.get("city"), str) and out["city"].strip() else None,
            "salary_from": _rub(out.get("salary_from")), "salary_to": _rub(out.get("salary_to"))}


def merge_need(rules: dict, out: dict | None) -> dict:
    """Гибрид, как работает продукт: поле из LLM, если она его заполнила, иначе — из правил."""
    if not out:
        return rules | {"parsed_by": "rules"}
    res = dict(rules)
    for k, v in need_from_llm(out).items():
        if v not in (None, "", []):
            res[k] = v
    res["nice_skills"] = [s for s in res["nice_skills"] if s not in res["must_skills"]]
    return res | {"parsed_by": "llm"}


def parse_need_text(text: str) -> dict:
    return merge_need(parse_need_rules(text), need_llm_extract(text))


# ------------------------------------------------------------------ пул кандидатов
def visible_candidates(db: Session) -> list[CandidateProfile]:
    """Кандидаты, видимые работодателям: есть категория, открыт к предложениям, дано согласие на публикацию."""
    cands = db.scalars(select(CandidateProfile).where(CandidateProfile.grade.is_not(None),
                                                      CandidateProfile.open_to_offers.is_(True))).all()
    consent = _publication_consents(db)
    return [c for c in cands if consent.get(c.user_id, False)]


def is_visible(db: Session, c: CandidateProfile) -> bool:
    if not (c.grade and c.open_to_offers):
        return False
    last = db.scalars(select(Consent).where(Consent.user_id == c.user_id, Consent.kind == "publication")
                      .order_by(Consent.id.desc())).first()
    return bool(last and last.granted)


def _publication_consents(db: Session) -> dict[int, bool]:
    rows = db.execute(select(Consent.user_id, Consent.granted, Consent.id).where(Consent.kind == "publication")
                      .order_by(Consent.id)).all()
    out: dict[int, bool] = {}
    for uid, granted, _ in rows:
        out[uid] = granted  # последнее по времени решение
    return out


def active_weights(db: Session) -> dict:
    m = db.scalars(select(RankingModel).where(RankingModel.active.is_(True)).order_by(RankingModel.id.desc())).first()
    return m.weights if m else dict(ranker.DEFAULT_WEIGHTS)


# ------------------------------------------------------------------ каталог категорий
def catalog(db: Session, need: Need | None = None) -> list[dict]:
    """Каталог категорий (специализация × грейд) с размером, долей ФСП и рыночными ожиданиями.
    Если передана потребность — с рекомендацией: сколько кандидатов категории закрывают must-навыки."""
    cands = visible_candidates(db)
    req = ranker.Requirement.from_obj(need) if need else None
    groups: dict[tuple, list] = {}
    for c in cands:
        groups.setdefault((c.specialization, c.grade), []).append(c)
    out = []
    for sp in SPECIALIZATIONS:
        for g in GRADE_ORDER:
            members = groups.get((sp.slug, g), [])
            sal = [c.salary_from for c in members if c.salary_from]
            item = {"specialization": sp.slug, "specialization_name": sp.name, "grade": g,
                    "grade_name": GRADE_BY_SLUG[g]["name"], "count": len(members),
                    "with_fsp": sum(1 for c in members if ((c.fsp_data or {}).get("summary") or {}).get("has_history")),
                    "salary_median": int(statistics.median(sal)) if sal else None,
                    "salary_p25": int(statistics.quantiles(sal, n=4)[0]) if len(sal) >= 4 else None,
                    "salary_p75": int(statistics.quantiles(sal, n=4)[2]) if len(sal) >= 4 else None}
            if req:
                relation = _relation(req, sp.slug, g)
                if relation is None:
                    continue
                item["relation"] = relation
                if members:
                    feats = [ranker.features(req, c)[1] for c in members]
                    item["matching"] = sum(1 for d in feats if d["must_total"] == 0 or d["must_covered"] >= max(1, round(0.6 * d["must_total"])))
                else:
                    item["matching"] = 0
            out.append(item)
    if req:
        order = {"exact": 0, "adjacent_grade": 1, "adjacent_spec": 2}
        out.sort(key=lambda x: (order[x["relation"]], -x.get("matching", 0)))
    return out


def _relation(req: ranker.Requirement, spec: str, grade: str) -> str | None:
    if spec == req.specialization and (grade in req.grades or not req.grades):
        return "exact"
    if spec == req.specialization and any(abs(GRADE_ORDER.index(grade) - GRADE_ORDER.index(g)) == 1 for g in req.grades):
        return "adjacent_grade"
    if spec in ADJACENT_SPECS.get(req.specialization, ()) and grade in req.grades:
        return "adjacent_spec"
    return None


# ------------------------------------------------------------------ выдача по потребности
def apply_filters(rows: list[dict], f: dict) -> list[dict]:
    out = []
    for r in rows:
        c = r["candidate"]
        if f.get("grades") and c.grade not in f["grades"]:
            continue
        summ = fsp_scoring.ensure_summary(c.fsp_data)
        if f.get("has_fsp") and not summ.get("has_history"):
            continue
        if f.get("fsp_prize") and not summ.get("prizes"):
            continue
        if f.get("skills"):
            ok = all(((c.skill_scores or {}).get(s) or {}).get("score", 0) >= f.get("min_skill_score", 50)
                     for s in f["skills"])
            if not ok:
                continue
        if f.get("salary_max") and c.salary_from and c.salary_from > f["salary_max"]:
            continue
        if f.get("formats") and not (set(c.work_formats or []) & set(f["formats"])):
            continue
        if f.get("city") and c.city != f["city"] and "remote" not in (c.work_formats or []):
            continue
        if f.get("must_full") and r["explanation"]["must_covered"] < r["explanation"]["must_total"]:
            continue
        if f.get("min_score") and r["score"] < f["min_score"]:
            continue
        out.append(r)
    return out


def need_results(db: Session, need: Need, filters: dict | None = None, include_adjacent: bool | None = None,
                 include_borderline: bool = True) -> dict:
    filters = filters or {}
    req = ranker.Requirement.from_obj(need)
    weights = active_weights(db)
    ranked = ranker.rank(req, visible_candidates(db), weights, include_adjacent, include_borderline=include_borderline)
    filtered = apply_filters(ranked, filters)
    pinned_ids = {e.candidate_id: e for e in db.scalars(select(ShortlistEntry).where(ShortlistEntry.need_id == need.id))}
    shown_ids = {r["candidate"].id for r in filtered}
    # закреплённые в подборке кандидаты не теряются при уточнении фильтров
    hidden_pinned = [r for r in ranked if r["candidate"].id in pinned_ids and r["candidate"].id not in shown_ids]
    invited = {i.candidate_id: i.status for i in db.scalars(select(Invitation).where(Invitation.need_id == need.id))}
    return {"total_in_category": len(ranked), "total": len(filtered), "items": filtered, "pinned_hidden": hidden_pinned,
            "pinned_ids": list(pinned_ids), "invited": invited, "weights": weights}


def search(db: Session, f: dict) -> list[dict]:
    """Поиск по всему банку: фильтры + сортировка по силе подтверждённого профиля (тест + ФСП)."""
    rows = []
    for c in visible_candidates(db):
        if f.get("specialization") and c.specialization != f["specialization"]:
            continue
        if f.get("grade") and c.grade != f["grade"]:
            continue
        summ = fsp_scoring.ensure_summary(c.fsp_data)
        if f.get("has_fsp") and not summ.get("has_history"):
            continue
        if f.get("fsp_prize") and not summ.get("prizes"):
            continue
        if f.get("skills") and not all(((c.skill_scores or {}).get(s) or {}).get("score", 0) >= f.get("min_skill_score", 50)
                                       for s in f["skills"]):
            continue
        if f.get("salary_max") and c.salary_from and c.salary_from > f["salary_max"]:
            continue
        if f.get("formats") and not (set(c.work_formats or []) & set(f["formats"])):
            continue
        if f.get("q"):
            q = f["q"].lower()
            hay = " ".join([c.about or "", " ".join(SKILL_BY_SLUG[s].name for s in (c.claimed_skills or []) if s in SKILL_BY_SLUG)]).lower()
            if q not in hay:
                continue
        req = ranker.Requirement(specialization=c.specialization, grades=[c.grade], must_skills=f.get("skills") or [])
        feats, detail = ranker.features(req, c)
        strength = round(100 * (0.6 * feats["test_strength"] + 0.3 * feats["fsp"] + 0.1 * feats["freshness"]), 1)
        rows.append({"candidate": c, "score": strength, "features": feats,
                     "explanation": ranker.explain(req, c, feats, detail)})
    if f.get("sort") == "fsp":  # сначала самые сильные результаты ФСП (под выбранные навыки, если они заданы)
        rows.sort(key=lambda r: (-r["features"]["fsp"], -r["score"], r["candidate"].id))
    else:
        rows.sort(key=lambda r: (-r["score"], r["candidate"].id))
    return rows


# ------------------------------------------------------------------ обратная связь по отказам
def employer_insights(db: Session, company_id: int) -> dict:
    """Аналитика по исходам приглашений: доля принятых, причины отказов, рекомендации."""
    invs = db.scalars(select(Invitation).where(Invitation.company_id == company_id)).all()
    total = len(invs)
    answered = [i for i in invs if i.status in ("accepted", "declined")]
    accepted = sum(1 for i in answered if i.status == "accepted")
    reasons = Counter(i.decline_reason for i in invs if i.status == "declined")
    names = {r["slug"]: r["name"] for r in DECLINE_REASONS}
    tips = []
    if reasons.get("salary_low", 0) >= 2 or (answered and reasons.get("salary_low", 0) / max(1, len(answered)) >= 0.3):
        cats = Counter((i.candidate.specialization, i.candidate.grade) for i in invs if i.status == "declined"
                       and i.decline_reason == "salary_low")
        for (sp, g), _ in cats.most_common(2):
            med = _salary_median(db, sp, g)
            offered = [i.salary_to for i in invs if i.candidate.specialization == sp and i.candidate.grade == g]
            if med and offered:
                gap = round(100 * (med - statistics.median(offered)) / med)
                if gap > 0:
                    tips.append(f"{SPEC_BY_SLUG[sp].name}, {GRADE_BY_SLUG[g]['name']}: медиана ожиданий "
                                f"{med // 1000} тыс. ₽, ваша вилка до {int(statistics.median(offered)) // 1000} тыс. ₽ "
                                f"(на {gap}% ниже рынка категории)")
    if reasons.get("stack_mismatch", 0) >= 2:
        tips.append("Кандидаты отмечают несовпадение стека: уточните обязательные навыки в потребности — "
                    "подборка учтёт их при ранжировании")
    if reasons.get("grade_mismatch", 0) >= 2:
        tips.append("Часть кандидатов считает уровень позиции несоответствующим: проверьте грейд в потребности")
    if reasons.get("format_mismatch", 0) >= 2:
        tips.append("Частая причина отказа — формат работы: рассмотрите гибрид или удалёнку")
    return {"sent": total, "answered": len(answered), "accepted": accepted,
            "accept_rate": round(accepted / len(answered), 2) if answered else None,
            "decline_reasons": [{"slug": k, "name": names.get(k, k), "count": v} for k, v in reasons.most_common()],
            "tips": tips}


def _salary_median(db: Session, spec: str, grade: str) -> int | None:
    vals = [c.salary_from for c in visible_candidates(db) if c.specialization == spec and c.grade == grade and c.salary_from]
    return int(statistics.median(vals)) if vals else None


def candidate_insights(db: Session, cand: CandidateProfile) -> dict:
    """Подсказка кандидату: какие навыки чаще всего требуют в его категории и что из них не подтверждено."""
    if not cand.specialization:
        return {"top_skills": [], "unconfirmed": [], "next_grade": None}
    needs = db.scalars(select(Need).where(Need.specialization == cand.specialization, Need.status == "active")).all()
    cnt = Counter(s for n in needs if not cand.grade or cand.grade in (n.grades or []) for s in (n.must_skills or []))
    if not cnt:  # в точной категории запросов нет — смотрим всю специализацию
        cnt = Counter(s for n in needs for s in (n.must_skills or []))
    top = [s for s, _ in cnt.most_common(8)]
    unconfirmed = [s for s in top if ((cand.skill_scores or {}).get(s) or {}).get("n", 0) == 0]
    weak = [s for s in top if 0 < ((cand.skill_scores or {}).get(s) or {}).get("score", 100) < 50]
    declines = Counter(i.decline_reason for i in db.scalars(select(Invitation).where(Invitation.candidate_id == cand.id,
                                                                                         Invitation.status == "declined")))
    return {"top_skills": [{"slug": s, "name": SKILL_BY_SLUG[s].name, "count": cnt[s]} for s in top if s in SKILL_BY_SLUG],
            "unconfirmed": [SKILL_BY_SLUG[s].name for s in unconfirmed if s in SKILL_BY_SLUG],
            "weak": [SKILL_BY_SLUG[s].name for s in weak if s in SKILL_BY_SLUG],
            "next_grade": grade_shift(cand.grade, 1) if cand.grade else None,
            "my_decline_reasons": dict(declines)}
