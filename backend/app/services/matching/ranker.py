"""Ранжирование кандидатов под потребность работодателя с объяснением.

Каждый фактор нормирован в [0, 1]; итог — взвешенная сумма ×100. Веса стартуют с экспертных и
дообучаются на исходах приглашений (см. ltr.py). Для каждого кандидата строится объяснение:
вклад каждого фактора + конкретные доказательства (оценки навыков по тесту, достижения ФСП, условия).

Ключевой принцип ТЗ: выдача строится по категории, присвоенной тестированием, а не по резюме.
Навык, заявленный только в резюме, учитывается с низким весом и помечается «не подтверждён».
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.fsp import scoring as fsp_scoring
from app.services.testing.irt import theta_to_score
from app.taxonomy import ADJACENT_SPECS, GRADE_BY_SLUG, GRADE_ORDER, SKILL_BY_SLUG, grade_cut, grade_shift

FACTORS = ["skill_fit", "grade_fit", "test_strength", "fsp", "freshness", "salary_fit", "format_fit"]
FACTOR_NAMES = {
    "skill_fit": "Навыки под задачу", "grade_fit": "Грейд", "test_strength": "Сила результата теста",
    "fsp": "Достижения ФСП", "freshness": "Актуальность профиля", "salary_fit": "Зарплатные ожидания",
    "format_fit": "Формат работы",
}
# ФСП — 0,15 (было 0,12): после экспертизы результат ФСП считается под конкретный запрос (см. fsp_for_request)
# и поэтому заслуживает большего веса; навыки 0,36 (было 0,38), актуальность 0,05 (было 0,06).
DEFAULT_WEIGHTS = {"skill_fit": 0.36, "grade_fit": 0.12, "test_strength": 0.18, "fsp": 0.15, "freshness": 0.05,
                   "salary_fit": 0.09, "format_fit": 0.05}

# Требуемая оценка навыка (0–100) для грейда = оценка в точке порога грейда на шкале θ
REQ_SCORE = {g: (theta_to_score(GRADE_BY_SLUG[g]["cut"]) if GRADE_BY_SLUG[g]["cut"] > -50 else 15) for g in GRADE_ORDER}


@dataclass
class Requirement:
    specialization: str
    grades: list[str]
    must_skills: list[str] = field(default_factory=list)
    nice_skills: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    city: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    allow_adjacent: bool = False

    @classmethod
    def from_obj(cls, o) -> "Requirement":
        grades = list(getattr(o, "grades", None) or [getattr(o, "grade", None)] or [])
        wf = getattr(o, "work_formats", None) or ([o.work_format] if getattr(o, "work_format", None) else [])
        return cls(specialization=o.specialization, grades=[g for g in grades if g], must_skills=list(o.must_skills or []),
                   nice_skills=list(o.nice_skills or []), work_formats=list(wf), city=getattr(o, "city", None),
                   salary_from=o.salary_from, salary_to=o.salary_to, allow_adjacent=getattr(o, "allow_adjacent", False))


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# Кандидат «на границе грейда»: по тесту — Middle, но вероятность того, что его уровень выше порога Senior,
# не меньше 30%. У порога тест ошибается чаще всего (точность решения там ~60–65%, это предел для теста такой
# длины), поэтому такие кандидаты показываются и в выдаче на соседний грейд выше — с пометкой и вероятностью,
# после кандидатов точной категории. Категория при этом не меняется.
BORDER_P = 0.3


def borderline_up(cand) -> tuple[str | None, float]:
    """(грейд выше, вероятность быть на его уровне) по оценке теста θ̂ и её погрешности."""
    if not cand.grade or cand.theta is None or cand.grade == "senior":
        return None, 0.0
    nxt = grade_shift(cand.grade, +1)
    if not nxt:
        return None, 0.0
    se = max(0.15, float(getattr(cand, "theta_se", None) or 0.45))
    z = (cand.theta - grade_cut(nxt)) / se
    return nxt, 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _fsp_summary(cand) -> dict:
    return fsp_scoring.ensure_summary(getattr(cand, "fsp_data", None))


def skill_evidence(cand, skill: str, target_grade: str) -> tuple[float, dict]:
    """Степень подтверждения навыка: тест и результат ФСП — независимые подтверждения, резюме — слабое.

    Тест + ФСП объединяются как «или» независимых свидетельств: сильный результат ФСП закрывает до половины
    оставшегося до 1 разрыва. Только ФСП — от 0,4 до 0,85 в зависимости от силы результатов: это проверенный
    факт, и он весит заметно больше, чем навык, заявленный только в резюме (0,25)."""
    req = REQ_SCORE.get(target_grade, 50)
    sc = (cand.skill_scores or {}).get(skill)
    fsp_sk = _fsp_summary(cand).get("skills", {}).get(skill)
    fsp_ev = (fsp_sk or {}).get("evidence", [])[:2]
    if sc and sc.get("n", 0) > 0:
        # чем меньше заданий, тем мягче вывод: SE расширяет «полосу» вокруг порога
        width = 6 + 10 * min(1.0, sc.get("se", 0.6))
        fit = _sig((sc["score"] - req) / width)
        if fsp_sk:
            fit = 1 - (1 - fit) * (1 - 0.5 * fsp_sk.get("level", 0))
        return fit, {"source": "test", "score": sc["score"], "n": sc["n"], "required": req,
                     "confidence": sc.get("confidence"), "fsp": bool(fsp_sk), "fsp_evidence": fsp_ev}
    if fsp_sk:
        lvl = fsp_sk.get("level", 0)
        return min(0.85, 0.4 + 0.45 * lvl), {"source": "fsp", "level": round(lvl, 2), "evidence": fsp_ev}
    if skill in (cand.claimed_skills or []):
        return 0.25, {"source": "resume"}
    return 0.0, {"source": "none"}


FSP_RELEVANT = 0.35  # с какой связи с запросом результат ФСП попадает в краткое объяснение «под ваш запрос»


def fsp_for_request(req: Requirement, cand) -> tuple[float, dict]:
    """Сила достижений ФСП под этот запрос: Σ сила результата × релевантность запросу, нормировано в [0, 1).

    Релевантность достижения = 0,4 × близость дисциплины (и роли в команде) специализации запроса
    + 0,6 × доля обязательных (вес 2) и желательных (вес 1) навыков запроса, которые результат подтверждает;
    половина взвешенных требований засчитывается как полное совпадение. Без навыков в запросе — только близость."""
    summ = _fsp_summary(cand)
    items = summ.get("items") or []
    if not items:
        return 0.0, {"has_history": bool(summ.get("has_history")), "items": []}
    want = {s: 2.0 for s in req.must_skills}
    for s in req.nice_skills:
        want.setdefault(s, 1.0)
    total_w = sum(want.values())
    scored = []
    for it in items:
        spec_rel = fsp_scoring.spec_relevance({"discipline": it["discipline"], "role": it.get("role")}, req.specialization)
        sk = it.get("skills") or {}
        if total_w:
            cover = sum(w * sk.get(s, 0.0) for s, w in want.items()) / total_w
            rel = 0.4 * spec_rel + 0.6 * min(1.0, 2 * cover)
        else:
            cover, rel = 0.0, spec_rel
        matched = [s for s in want if sk.get(s, 0) >= 0.4]
        scored.append((it["strength"] * rel, rel, matched, it))
    # разряд подтверждает уровень в своих дисциплинах — под запрос он весит столько, насколько они с ним связаны
    max_rel = max((x[1] for x in scored), default=0.0)
    rank_bonus = 0.5 * fsp_scoring.RANK_W.get(summ.get("sport_rank") or "", 0.0) * max_rel
    raw = sum(x[0] for x in scored) + rank_bonus
    value = 1.0 - math.exp(-raw / 2.5)
    scored.sort(key=lambda x: -x[0])
    top = [{"event": it["event"], "result": it["result"], "level": it.get("level_name"), "date": it["date"],
            "discipline": it.get("discipline_name"), "role": it.get("role"), "relevance": round(rel, 2),
            "points": round(p, 3), "matched_skills": matched}
           for p, rel, matched, it in scored[:3] if p > 0]
    return value, {"has_history": True, "items": top, "sport_rank": summ.get("sport_rank"),
                   "prizes": summ.get("prizes", 0), "total": summ.get("total", 0)}


def _target_grade(req: Requirement, cand) -> str:
    if cand.grade in req.grades:
        return cand.grade
    return req.grades[0] if req.grades else (cand.grade or "middle")


def features(req: Requirement, cand, now: datetime | None = None) -> tuple[dict, dict]:
    now = now or datetime.now(timezone.utc)
    detail: dict = {}
    tg = _target_grade(req, cand)

    # 1. навыки
    weights = {s: 2.0 for s in req.must_skills}
    for s in req.nice_skills:
        weights.setdefault(s, 1.0)
    per = {}
    if weights:
        tot = 0.0
        for s, w in weights.items():
            fit, info = skill_evidence(cand, s, tg)
            per[s] = {"fit": round(fit, 3), "weight": w, "must": s in req.must_skills, **info}
            tot += w * fit
        skill_fit = tot / sum(weights.values())
    else:
        skill_fit = _sig(((cand.theta or 0) - grade_cut(tg) if tg != "intern" else 0) / 0.5)
    must_ok = [s for s in req.must_skills if per.get(s, {}).get("fit", 0) >= 0.5]
    detail["skills"] = per
    detail["must_covered"] = len(must_ok)
    detail["must_total"] = len(req.must_skills)

    # 2. грейд
    nxt, p_up = borderline_up(cand)
    detail["borderline"] = {"to": nxt, "p": round(p_up, 2)} if nxt and p_up >= BORDER_P else None
    if cand.grade in req.grades or not req.grades:
        grade_fit = 1.0
    elif nxt in req.grades and p_up >= BORDER_P:
        grade_fit = p_up  # вероятность того, что уровень кандидата — грейд запроса; ниже кандидатов точной категории
    else:
        dist = min(abs(GRADE_ORDER.index(cand.grade) - GRADE_ORDER.index(g)) for g in req.grades) if cand.grade else 3
        grade_fit = 0.4 if dist == 1 else 0.0
    if cand.specialization != req.specialization:
        grade_fit *= 0.6  # смежная специализация

    # 3. сила результата теста внутри категории (насколько θ выше порога своего грейда)
    if cand.theta is not None and cand.grade:
        cut = grade_cut(cand.grade) if cand.grade != "intern" else -2.0
        test_strength = _sig((cand.theta - cut - 0.5) / 0.45)
    else:
        test_strength = 0.0

    # 4. ФСП: сила результатов под этот запрос
    fsp, detail["fsp"] = fsp_for_request(req, cand)

    # 5. свежесть: последний тест / регулярное задание
    last = cand.last_activity_at or cand.grade_assigned_at
    days = (now - last).days if last else 365
    freshness = math.exp(-max(0, days) / 180)

    # 6. зарплата: пересечение вилки работодателя с ожиданиями
    salary_over = 0.0
    ef, et = req.salary_from, req.salary_to
    cf, ct = cand.salary_from, cand.salary_to
    if not (et or ef) or not (cf or ct):
        salary_fit = 0.7
    elif et and cf and cf > et:
        salary_fit = max(0.0, 1 - 3 * (cf - et) / et)  # кандидат хочет больше максимума вилки
        salary_over = (cf - et) / et
    elif ef and ct and ct < ef:
        salary_fit = 0.85  # вилка выше ожиданий — для кандидата это не минус
    else:
        salary_fit = 1.0

    # 7. формат и город
    cfm = set(cand.work_formats or [])
    rfm = set(req.work_formats or [])
    if not cfm or not rfm:
        format_fit = 0.7
    elif cfm & rfm:
        format_fit = 1.0 if ("remote" in (cfm & rfm) or not req.city or not cand.city or req.city == cand.city
                             or cand.relocation) else 0.5
    else:
        format_fit = 0.2

    f = {"skill_fit": skill_fit, "grade_fit": grade_fit, "test_strength": test_strength, "fsp": fsp,
         "freshness": freshness, "salary_fit": salary_fit, "format_fit": format_fit, "salary_over": salary_over}
    detail["salary"] = {"candidate": [cf, ct], "employer": [ef, et]}
    detail["days_since_activity"] = days
    return {k: round(v, 4) for k, v in f.items()}, detail


# Несовпадение по деньгам — множитель, а не только слагаемое. Валидация показала: при слагаемом с весом 0,09
# сильные по тесту и ФСП кандидаты, чьи ожидания выше максимума вилки, поднимались наверх, хотя почти наверняка
# откажут. Теперь итог умножается на (0,6 + 0,4 × соответствие по зарплате): ожидания в пределах вилки — без
# изменений, на треть выше максимума — итог ниже на 40%.
SALARY_GATE = 0.4


def salary_multiplier(feats: dict) -> float:
    """Только когда ожидания кандидата выше максимума вилки (salary_over — на сколько, доля от максимума)."""
    over = feats.get("salary_over", 0.0) or 0.0
    return 1.0 - SALARY_GATE * min(1.0, 3 * over)


def score(feats: dict, weights: dict | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    return round(100 * sum(w[k] * feats[k] for k in FACTORS) * salary_multiplier(feats), 1)


def _fmt_rub(x: int | None) -> str:
    return f"{x // 1000} тыс." if x else "—"


def explain(req: Requirement, cand, feats: dict, detail: dict, weights: dict | None = None) -> dict:
    """Краткое и подробное объяснение выдачи."""
    w = weights or DEFAULT_WEIGHTS
    contrib = {k: round(100 * w[k] * feats[k], 1) for k in FACTORS}
    sal_mult = salary_multiplier(feats)
    pros, cons = [], []
    sk = detail["skills"]
    # сначала обязательные навыки с наибольшим числом заданий — самые весомые доказательства
    tested = sorted([(s, v) for s, v in sk.items() if v["source"] == "test"],
                    key=lambda kv: (not kv[1]["must"], -kv[1]["n"], -kv[1]["score"]))
    for s, v in tested[:3]:
        name = SKILL_BY_SLUG[s].name if s in SKILL_BY_SLUG else s
        txt = f"{name}: {v['score']}/100 по тесту ({v['n']} задан.)"
        (pros if v["fit"] >= 0.5 else cons).append(txt + ("" if v["fit"] >= 0.5 else f" — ниже требуемых {v['required']}"))
    for s, v in sk.items():
        name = SKILL_BY_SLUG[s].name if s in SKILL_BY_SLUG else s
        if v["source"] == "fsp":
            ev = (v.get("evidence") or [{}])[0]
            pros.append(f"{name}: подтверждено ФСП" + (f" — {ev['result'].lower()}, {ev['event']}" if ev.get("result") else ""))
        elif v["source"] == "resume" and v["must"]:
            cons.append(f"{name}: только в резюме, тестом не подтверждено")
        elif v["source"] == "none" and v["must"]:
            cons.append(f"{name}: нет подтверждения")
    if detail["must_total"]:
        (pros if detail["must_covered"] == detail["must_total"] else cons).insert(
            0, f"Обязательные навыки: подтверждено {detail['must_covered']} из {detail['must_total']}")
    fd = detail.get("fsp") or {}
    best = (fd.get("items") or [None])[0]
    if best and best["relevance"] >= FSP_RELEVANT:
        where = ", ".join(x for x in (best.get("discipline"), (best.get("level") or "").lower()) if x)
        txt = f"ФСП под ваш запрос: {best['result'].lower()} — {where} ({best['date'][:4]})"
        if best["matched_skills"]:
            txt += ", подтверждает " + ", ".join(SKILL_BY_SLUG[x].name for x in best["matched_skills"][:3] if x in SKILL_BY_SLUG)
        # результат ФСП — независимое подтверждение, поэтому в кратком объяснении он идёт вторым, после навыков
        pros.insert(1 if pros else 0, txt)
    elif fd.get("has_history"):
        pros.append("Есть история ФСП, но результаты слабо связаны с запросом")
    if feats["salary_fit"] >= 0.99 and (cand.salary_from or cand.salary_to):
        pros.append(f"Ожидания {_fmt_rub(cand.salary_from)}–{_fmt_rub(cand.salary_to)} ₽ в пределах вилки")
    elif feats["salary_fit"] < 0.7:
        cons.append(f"Ожидания от {_fmt_rub(cand.salary_from)} ₽ выше вашей вилки"
                    + (f" — итог снижен на {round(100 * (1 - sal_mult))}%" if sal_mult < 0.95 else ""))
    if feats["format_fit"] <= 0.2:
        cons.append("Не совпадает формат работы")
    if detail["days_since_activity"] <= 30:
        pros.append(f"Профиль подтверждён {detail['days_since_activity']} дн. назад")
    elif detail["days_since_activity"] > 180:
        cons.append("Профиль давно не обновлялся")
    bl = detail.get("borderline")
    if bl and cand.grade not in req.grades:
        to = GRADE_BY_SLUG[bl["to"]]["name"]
        cons.append(f"По тесту {GRADE_BY_SLUG[cand.grade]['name']}" +
                    (f", на границе с {to}: вероятность уровня {to} {bl['p']:.0%}" if bl["p"] < 0.7 else
                     f", но уровень {to} вероятен ({bl['p']:.0%}): тест на {to} не пройден или не проходился"))
    elif feats["grade_fit"] < 1:
        cons.append("Грейд или специализация — смежные с запросом")
    top = sorted(((k, v) for k, v in contrib.items()), key=lambda kv: -kv[1])
    return {"summary": "; ".join(pros[:3]) if pros else "Совпадение по категории",
            "pros": pros, "cons": cons, "fsp": {**fd, "value": feats["fsp"], "points": contrib["fsp"]},
            "borderline": bl, "salary_multiplier": round(sal_mult, 3),
            "factors": [{"key": k, "name": FACTOR_NAMES[k], "value": feats[k], "weight": w[k], "points": v} for k, v in top],
            "skills": sk, "must_covered": detail["must_covered"], "must_total": detail["must_total"]}


def eligible(req: Requirement, cand, include_adjacent: bool | None = None, include_borderline: bool = True) -> bool:
    """Предфильтр по категории (специализация × грейд), присвоенной тестом. Кандидат на границе с грейдом запроса
    (borderline_up) проходит предфильтр, если include_borderline."""
    adj = req.allow_adjacent if include_adjacent is None else include_adjacent
    if not cand.grade or not cand.specialization:
        return False
    spec_ok = cand.specialization == req.specialization or (adj and cand.specialization in ADJACENT_SPECS.get(req.specialization, ()))
    if not spec_ok:
        return False
    if not req.grades or cand.grade in req.grades:
        return True
    if include_borderline:
        nxt, p_up = borderline_up(cand)
        if nxt in req.grades and p_up >= BORDER_P:
            return True
    if adj:
        return any(abs(GRADE_ORDER.index(cand.grade) - GRADE_ORDER.index(g)) == 1 for g in req.grades)
    return False


def rank(req: Requirement, cands: list, weights: dict | None = None, include_adjacent: bool | None = None,
         include_borderline: bool = True) -> list[dict]:
    out = []
    for c in cands:
        if not eligible(req, c, include_adjacent, include_borderline):
            continue
        f, d = features(req, c)
        out.append({"candidate": c, "score": score(f, weights), "features": f, "explanation": explain(req, c, f, d, weights)})
    out.sort(key=lambda r: (-r["score"], -(r["candidate"].theta or 0), r["candidate"].id))
    return out
