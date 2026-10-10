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

from app.services.testing.irt import theta_to_score
from app.taxonomy import ADJACENT_SPECS, GRADE_BY_SLUG, GRADE_ORDER, SKILL_BY_SLUG, grade_cut

FACTORS = ["skill_fit", "grade_fit", "test_strength", "fsp", "freshness", "salary_fit", "format_fit"]
FACTOR_NAMES = {
    "skill_fit": "Навыки под задачу", "grade_fit": "Грейд", "test_strength": "Сила результата теста",
    "fsp": "Достижения ФСП", "freshness": "Актуальность профиля", "salary_fit": "Зарплатные ожидания",
    "format_fit": "Формат работы",
}
DEFAULT_WEIGHTS = {"skill_fit": 0.38, "grade_fit": 0.12, "test_strength": 0.18, "fsp": 0.12, "freshness": 0.06,
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


def skill_evidence(cand, skill: str, target_grade: str) -> tuple[float, dict]:
    """Степень подтверждения навыка: тест > ФСП > только резюме."""
    req = REQ_SCORE.get(target_grade, 50)
    sc = (cand.skill_scores or {}).get(skill)
    fsp_sk = ((cand.fsp_data or {}).get("summary") or {}).get("skills", {}).get(skill)
    if sc and sc.get("n", 0) > 0:
        # чем меньше заданий, тем мягче вывод: SE расширяет «полосу» вокруг порога
        width = 6 + 10 * min(1.0, sc.get("se", 0.6))
        fit = _sig((sc["score"] - req) / width)
        if fsp_sk:
            fit = min(1.0, fit + 0.1 * fsp_sk.get("level", 0))
        return fit, {"source": "test", "score": sc["score"], "n": sc["n"], "required": req,
                     "confidence": sc.get("confidence"), "fsp": bool(fsp_sk)}
    if fsp_sk:
        lvl = fsp_sk.get("level", 0)
        return min(0.8, 0.35 + 0.5 * lvl), {"source": "fsp", "level": round(lvl, 2),
                                             "evidence": fsp_sk.get("evidence", [])[:2]}
    if skill in (cand.claimed_skills or []):
        return 0.25, {"source": "resume"}
    return 0.0, {"source": "none"}


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
    if cand.grade in req.grades or not req.grades:
        grade_fit = 1.0
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

    # 4. ФСП
    summ = (cand.fsp_data or {}).get("summary") or {}
    fsp = float((summ.get("score_by_spec") or {}).get(req.specialization, 0.0))

    # 5. свежесть: последний тест / регулярное задание
    last = cand.last_activity_at or cand.grade_assigned_at
    days = (now - last).days if last else 365
    freshness = math.exp(-max(0, days) / 180)

    # 6. зарплата: пересечение вилки работодателя с ожиданиями
    ef, et = req.salary_from, req.salary_to
    cf, ct = cand.salary_from, cand.salary_to
    if not (et or ef) or not (cf or ct):
        salary_fit = 0.7
    elif et and cf and cf > et:
        salary_fit = max(0.0, 1 - 3 * (cf - et) / et)  # кандидат хочет больше максимума вилки
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
         "freshness": freshness, "salary_fit": salary_fit, "format_fit": format_fit}
    detail["salary"] = {"candidate": [cf, ct], "employer": [ef, et]}
    detail["days_since_activity"] = days
    return {k: round(v, 4) for k, v in f.items()}, detail


def score(feats: dict, weights: dict | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    return round(100 * sum(w[k] * feats[k] for k in FACTORS), 1)


def _fmt_rub(x: int | None) -> str:
    return f"{x // 1000} тыс." if x else "—"


def explain(req: Requirement, cand, feats: dict, detail: dict, weights: dict | None = None) -> dict:
    """Краткое и подробное объяснение выдачи."""
    w = weights or DEFAULT_WEIGHTS
    contrib = {k: round(100 * w[k] * feats[k], 1) for k in FACTORS}
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
            pros.append(f"{name}: подтверждено результатами ФСП")
        elif v["source"] == "resume" and v["must"]:
            cons.append(f"{name}: только в резюме, тестом не подтверждено")
        elif v["source"] == "none" and v["must"]:
            cons.append(f"{name}: нет подтверждения")
    if detail["must_total"]:
        (pros if detail["must_covered"] == detail["must_total"] else cons).insert(
            0, f"Обязательные навыки: подтверждено {detail['must_covered']} из {detail['must_total']}")
    summ = (cand.fsp_data or {}).get("summary") or {}
    if summ.get("has_history"):
        best = max((d for d in summ.get("by_discipline", {}).values()), key=lambda d: d["strength"], default=None)
        if best:
            pros.append(f"ФСП: {best['name']}, лучшее место {best['best_place']}"
                        + (f", призовых мест: {summ['prizes']}" if summ.get("prizes") else "")
                        + (f", {summ['sport_rank']}" if summ.get("sport_rank") else ""))
    if feats["salary_fit"] >= 0.99 and (cand.salary_from or cand.salary_to):
        pros.append(f"Ожидания {_fmt_rub(cand.salary_from)}–{_fmt_rub(cand.salary_to)} ₽ в пределах вилки")
    elif feats["salary_fit"] < 0.7:
        cons.append(f"Ожидания от {_fmt_rub(cand.salary_from)} ₽ выше вашей вилки")
    if feats["format_fit"] <= 0.2:
        cons.append("Не совпадает формат работы")
    if detail["days_since_activity"] <= 30:
        pros.append(f"Профиль подтверждён {detail['days_since_activity']} дн. назад")
    elif detail["days_since_activity"] > 180:
        cons.append("Профиль давно не обновлялся")
    if feats["grade_fit"] < 1:
        cons.append("Грейд или специализация — смежные с запросом")
    top = sorted(((k, v) for k, v in contrib.items()), key=lambda kv: -kv[1])
    return {"summary": "; ".join(pros[:3]) if pros else "Совпадение по категории",
            "pros": pros, "cons": cons,
            "factors": [{"key": k, "name": FACTOR_NAMES[k], "value": feats[k], "weight": w[k], "points": v} for k, v in top],
            "skills": sk, "must_covered": detail["must_covered"], "must_total": detail["must_total"]}


def eligible(req: Requirement, cand, include_adjacent: bool | None = None) -> bool:
    """Предфильтр по категории (специализация × грейд), присвоенной тестом."""
    adj = req.allow_adjacent if include_adjacent is None else include_adjacent
    if not cand.grade or not cand.specialization:
        return False
    spec_ok = cand.specialization == req.specialization or (adj and cand.specialization in ADJACENT_SPECS.get(req.specialization, ()))
    if not spec_ok:
        return False
    if not req.grades or cand.grade in req.grades:
        return True
    if adj:
        return any(abs(GRADE_ORDER.index(cand.grade) - GRADE_ORDER.index(g)) == 1 for g in req.grades)
    return False


def rank(req: Requirement, cands: list, weights: dict | None = None, include_adjacent: bool | None = None) -> list[dict]:
    out = []
    for c in cands:
        if not eligible(req, c, include_adjacent):
            continue
        f, d = features(req, c)
        out.append({"candidate": c, "score": score(f, weights), "features": f, "explanation": explain(req, c, f, d, weights)})
    out.sort(key=lambda r: (-r["score"], -(r["candidate"].theta or 0), r["candidate"].id))
    return out
