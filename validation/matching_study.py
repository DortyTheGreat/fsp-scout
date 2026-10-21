"""Валидация механики подбора на тестовом наборе пар «вакансия – кандидат».

Мир симуляции: у каждого кандидата есть скрытые истинные навыки. Он проходит НАСТОЯЩИЙ адаптивный тест
(тот же код, что в продукте), пишет резюме (с типичным «раздуванием» навыков), имеет ожидания по
зарплате и формату, у части — история ФСП. Эталонная релевантность пары считается по ИСТИННЫМ навыкам,
грейду и условиям — ни один ранжировщик её не видит.

Сравниваем:
  • случайный выбор в специализации;
  • поиск по ключевым словам резюме и заявленному опыту (как на универсальных площадках);
  • только категория по тесту (случайный порядок внутри категории);
  • наш ранжировщик без ФСП и полный.
Метрики: Precision@10/20 (доля релевантных в топе — метрика из критериев жюри), nDCG@10, MRR, Recall@50.
Отдельно — дообучение весов на исходах приглашений (LTR): рост ожидаемой доли принятых приглашений.

Запуск: python validation/matching_study.py [--candidates 2000 --vacancies 60]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from common import (OUT, PALETTE, blueprint_for, irt, make_pool, new_candidate, run_cat, setup_matplotlib)
from app.services.fsp import scoring as fsp_scoring
from app.services.matching import ltr, ranker
from baselines import ranker_before_review as ranker_v1
from app.services.testing.bank import TEMPLATES
from app.taxonomy import GRADE_ORDER, SPEC_BY_SLUG, grade_cut, grade_from_theta

SPECS = list(SPEC_BY_SLUG)
SPEC_W = [34, 20, 15, 15, 16]
SAL = {"intern": 60, "junior": 110, "middle": 230, "senior": 380}
NOW = datetime.now(timezone.utc)


def claimed_grade(theta, rng, sd=0.5):
    g = grade_from_theta(theta + rng.normal(0.25, sd))
    return "junior" if g == "intern" else g


# Честность резюме. Метаанализ Mabe & West (1982): средняя корреляция самооценки способностей с
# измеренными ≈ 0.29. Шум sd в заявленном уровне (θ ~ N(0,1)): corr ≈ 1/sqrt(1+sd²).
RESUME_NOISE = {"почти честные резюме (corr ≈ 0.9)": {"grade_sd": 0.5, "stuff": 0.2, "years_sd": 0.45},
                "умеренно (corr ≈ 0.6)": {"grade_sd": 1.3, "stuff": 0.4, "years_sd": 0.8},
                "реалистично (corr ≈ 0.45)": {"grade_sd": 2.0, "stuff": 0.5, "years_sd": 1.0}}


# ------------------------------------------------------------------ история ФСП в мире симуляции
# Предпосылка ТЗ: результаты соревнований — объективное подтверждение практических навыков. В симуляции место
# участника определяется ИСТИННЫМИ навыками, которые проверяет этот результат (дисциплина + стек + роль),
# с шумом: командный состав, удача, сила поля. Уровень шума — параметр (FSP_NOISE); при «случайном» ФСП
# место вообще не связано с навыками — проверка того, что учёт ФСП не вредит, когда он ничего не значит.
FSP_DISC = {"backend": {"product": 0.55, "algorithmic": 0.3, "security": 0.15},
            "frontend": {"product": 0.7, "algorithmic": 0.3},
            "data_science": {"product": 0.5, "algorithmic": 0.4, "robotics": 0.1},
            "devops": {"product": 0.4, "security": 0.5, "algorithmic": 0.1},
            "qa": {"product": 0.5, "security": 0.4, "algorithmic": 0.1}}
FSP_ROLE = {"backend": "Бэкенд-разработчик", "frontend": "Фронтенд-разработчик", "data_science": "ML-инженер",
            "devops": "DevOps", "qa": "Участник"}
SKILL_TAG = {"python": "python", "web_frameworks": "fastapi", "postgresql": "postgresql", "sql": "sql", "react": "react",
             "docker": "docker", "kubernetes": "kubernetes", "caching_queues": "redis", "deep_learning": "pytorch",
             "pandas": "pandas", "ml": "catboost", "typescript": "typescript", "javascript": "nodejs", "linux": "linux",
             "networking": "networking"}
LEVEL_P = {"regional": 0.45, "interregional": 0.25, "national": 0.25, "international": 0.05}
LEVEL_FIELD = {"regional": (15, 25, 40, 60), "interregional": (40, 60, 80, 120), "national": (80, 120, 200, 350),
               "international": (200, 350, 500)}
LEVEL_OFFSET = {"regional": -0.5, "interregional": 0.0, "national": 0.6, "international": 1.0}
FSP_NOISE = {"реалистично (шум 0.8)": 0.8, "слабая связь с навыками (шум 1.6)": 1.6, "случайные места": None}


def make_fsp(rng, c, spec: str, noise: float | None) -> dict:
    from math import erf, sqrt
    n_res = int(rng.integers(1, 6))
    items = []
    discs = list(FSP_DISC[spec])
    pd_ = np.array([FSP_DISC[spec][d] for d in discs])
    for k in range(n_res):
        disc = discs[rng.choice(len(discs), p=pd_ / pd_.sum())]
        level = list(LEVEL_P)[rng.choice(4, p=list(LEVEL_P.values()))]
        total = int(rng.choice(LEVEL_FIELD[level]))
        fmt = "individual" if disc == "algorithmic" and rng.random() < 0.5 else "team"
        a = {"id": f"sim-{c.theta:.3f}-{k}", "event_name": f"Соревнования ({disc})", "discipline": disc,
             "discipline_name": disc, "level": level, "level_name": level, "format": fmt, "participants_total": total,
             "date": (NOW - timedelta(days=int(rng.integers(30, 1400)))).date().isoformat(), "verified": True}
        if disc == "product":
            sk = [s for s in SPEC_BY_SLUG[spec].core_skills if s in SKILL_TAG]
            if sk:
                w = np.exp(np.array([c.skill_theta.get(s, c.theta) for s in sk]))  # на хакатонах берут сильный стек
                pick = rng.choice(len(sk), size=min(len(sk), int(rng.integers(2, 5))), replace=False, p=w / w.sum())
                a["stack"] = [SKILL_TAG[sk[i]] for i in pick]
            a["role"] = FSP_ROLE[spec]
        elif disc == "algorithmic":
            a["stack"] = ["python"] if rng.random() < 0.5 else ["cpp"]
        a["skills_true"] = list(fsp_scoring.achievement_skills(a))
        if noise is None:
            pct = float(rng.random())
        else:
            perf = np.mean([c.skill_theta.get(s, c.theta) for s in a["skills_true"]] or [c.theta])
            perf += rng.normal(0, noise + (0.4 if fmt == "team" else 0.0))
            z = (perf - LEVEL_OFFSET[level]) / 1.0
            pct = 0.5 * (1 + erf(z / sqrt(2)))
        a["place"] = max(1, min(total, int(round((1 - pct) * total)) + 1))
        if disc == "algorithmic":
            a["tasks_total"] = 10
            a["tasks_solved"] = int(max(0, min(10, round(pct * 10 + rng.normal(0, 1)))))
        items.append(a)
    best = min(x["place"] / x["participants_total"] for x in items)
    rank = "1 разряд" if best < 0.05 else ("2 разряд" if best < 0.15 else None)
    return {"items": items, "summary": fsp_scoring.summarize(items, rank, NOW.date()), "participant": {"sport_rank": rank}}


def make_world(n: int, seed: int, noise: dict | None = None):
    noise = noise or RESUME_NOISE["реалистично (corr ≈ 0.45)"]
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    pools = {s: make_pool(s, np.random.default_rng(seed + i)) for i, s in enumerate(SPECS)}
    bps = {s: blueprint_for(s, pools[s]) for s in SPECS}
    known = {s: {p.id: p for p in pools[s]} for s in SPECS}
    cands = []
    for i in range(n):
        spec = SPECS[rng.choice(len(SPECS), p=np.array(SPEC_W) / sum(SPEC_W))]
        c = new_candidate(rng, spec, skill_sd=0.55)
        g = claimed_grade(c.theta, rng, 0.5)            # грейд, на который человек идёт на тест
        g_resume = claimed_grade(c.theta, rng, noise["grade_sd"])  # уровень, который он пишет в резюме
        # путь кандидата как в продукте
        d, log, st = run_cat(c, pools[spec], g, rr, bps[spec], return_state=True)
        logs = list(log)
        assigned = g if d["passed"] else None
        target = g
        while assigned is None:
            lower = d["lower_grade"]
            if not lower or lower == "intern":
                assigned = "intern"
                break
            if d["can_accept_lower"]:
                assigned = lower
                break
            d, log2, st = run_cat(c, pools[spec], lower, rr, bps[spec], prior_obs=st.obs, return_state=True)
            logs += log2
            target = lower
            if d["passed"]:
                assigned = lower
        if assigned == "intern":
            continue  # без категории кандидат не виден работодателям
        theta_hat = d["theta"]
        # оценки навыков — как recompute_skill_scores в продукте
        per = {}
        for tid, _, u in logs:
            p = known[spec][tid]
            for s, w in TEMPLATES[tid].skills.items():
                per.setdefault(s, []).append(irt.Obs(p.a_known, p.b_known, p.c, 1.0 if u else 0.0, w))
        scores = {}
        for s, obs in per.items():
            th, se = irt.eap(obs, mu=theta_hat, sd=1.0)
            n_main = sum(1 for o in obs if o.w >= 0.5)
            scores[s] = {"score": irt.theta_to_score(th), "se": se, "n": n_main,
                         "confidence": "высокая" if se < 0.45 else ("средняя" if se < 0.65 else "низкая")}
        true_g = grade_from_theta(c.theta)
        # резюме: реальные сильные навыки + «раздувание» + шум
        core = list(SPEC_BY_SLUG[spec].core_skills)
        claimed = [s for s in core if (c.skill_theta[s] > grade_cut(true_g) - 0.3 and rng.random() < 0.85)
                   or rng.random() < noise["stuff"]]
        years = max(0.0, {"intern": 0.3, "junior": 1.0, "middle": 3.0, "senior": 6.0}[true_g] * float(rng.lognormal(0, noise["years_sd"])))
        sal = SAL[true_g] * float(rng.lognormal(0, 0.15)) * 1000
        has_fsp = rng.random() < 0.15 + 0.35 / (1 + math.exp(-1.5 * c.theta))
        fsp_rng = np.random.default_rng(seed * 100003 + i)
        fsp_variants = {lbl: (make_fsp(np.random.default_rng(seed * 100003 + i), c, spec, nz) if has_fsp else {})
                        for lbl, nz in FSP_NOISE.items()}
        fsp = fsp_variants["реалистично (шум 0.8)"]
        _ = fsp_rng
        fmts = [["remote"], ["hybrid", "remote"], ["office", "hybrid"], ["hybrid"], ["office"]][int(rng.integers(0, 5))]
        cands.append(SimpleNamespace(
            id=i, specialization=spec, grade=assigned, theta=theta_hat, theta_se=d["se"], skill_scores=scores,
            claimed_skills=claimed,
            claimed_grade=g_resume, years=years, fsp_data=fsp, salary_from=int(sal), salary_to=int(sal * 1.2),
            work_formats=fmts, city="Москва", relocation=False,
            last_activity_at=NOW - timedelta(days=int(rng.integers(0, 300))), grade_assigned_at=None,
            true_theta=c.theta, true_skill=c.skill_theta, true_grade=true_g, fsp_variants=fsp_variants))
    return cands


def make_vacancies(n: int, seed: int, cands):
    rng = np.random.default_rng(seed + 99)
    vacs = []
    for i in range(n):
        spec = SPECS[rng.choice(len(SPECS), p=np.array(SPEC_W) / sum(SPEC_W))]
        grade = ["junior", "middle", "senior"][int(rng.integers(0, 3))]
        core = list(SPEC_BY_SLUG[spec].core_skills)
        must = list(rng.choice(core, size=int(rng.integers(3, 5)), replace=False))
        nice = [s for s in rng.choice(core, size=2, replace=False) if s not in must]
        med = SAL[grade] * 1000
        sf = int(med * rng.uniform(0.85, 1.0))
        vacs.append(SimpleNamespace(id=i, specialization=spec, grades=[grade], grade=grade, must_skills=must, nice_skills=nice,
                                    work_formats=[["remote"], ["hybrid"], ["office"], ["hybrid", "remote"]][int(rng.integers(0, 4))],
                                    city="Москва", salary_from=sf, salary_to=int(sf * rng.uniform(1.15, 1.35)), allow_adjacent=False))
    return vacs


def relevance(v, c) -> int:
    """Эталон: истинные навыки и грейд + условия. 3 — отличное совпадение, 0 — нерелевантен."""
    if c.specialization != v.specialization:
        return 0
    gi, vi = GRADE_ORDER.index(c.true_grade), GRADE_ORDER.index(v.grade)
    # сильнее на грейд — подходит, если сходятся деньги (это проверяет salary_ok); слабее — почти нет
    grade_match = 1.0 if gi == vi else 0.85 if gi == vi + 1 else 0.3 if gi == vi - 1 else 0.0
    cut = grade_cut(v.grade)
    skill_ok = np.mean([c.true_skill.get(s, c.true_theta) >= cut - 0.2 for s in v.must_skills])
    salary_ok = c.salary_from <= v.salary_to * 1.05
    fmt_ok = bool(set(c.work_formats) & set(v.work_formats)) or "remote" in c.work_formats and "remote" in v.work_formats
    r = grade_match * (0.4 + 0.6 * skill_ok) * (1.0 if salary_ok else 0.4) * (1.0 if fmt_ok else 0.6)
    return 3 if r >= 0.9 else 2 if r >= 0.6 else 1 if r >= 0.35 else 0


def rank_keyword(v, cands, rng):
    out = []
    band = {"junior": (0.3, 2), "middle": (2, 4.5), "senior": (4, 99)}[v.grade]
    for c in cands:
        if c.specialization != v.specialization:
            continue
        cl = set(c.claimed_skills)
        s = 2 * len(cl & set(v.must_skills)) + len(cl & set(v.nice_skills))
        s += 2 if c.claimed_grade == v.grade else 0
        s += 1 if band[0] <= c.years <= band[1] else 0
        out.append((s + rng.random() * 0.01, c))
    return [c for _, c in sorted(out, key=lambda x: -x[0])]


def rank_random(v, cands, rng):
    pool = [c for c in cands if c.specialization == v.specialization]
    rng.shuffle(pool)
    return pool


def rank_category(v, cands, rng):
    pool = [c for c in cands if c.specialization == v.specialization and c.grade == v.grade]
    rng.shuffle(pool)
    return pool


def rank_ours(v, cands, weights=None, adjacent=None, borderline=True):
    req = ranker.Requirement.from_obj(v)
    return [r["candidate"] for r in ranker.rank(req, cands, weights, include_adjacent=adjacent,
                                                include_borderline=borderline)]


def rank_v1(v, cands):
    """Ранжировщик промежуточной сдачи без изменений (validation/baselines/ranker_before_review.py)."""
    req = ranker_v1.Requirement.from_obj(v)
    return [r["candidate"] for r in ranker_v1.rank(req, cands)]


def metrics(ranked, v, all_rel_count):
    rel = [relevance(v, c) for c in ranked[:50]]
    hit = [r >= 2 for r in rel]
    p10 = float(np.mean(hit[:10])) if len(hit) >= 1 else 0.0
    p10 = sum(hit[:10]) / 10
    p20 = sum(hit[:20]) / 20
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rel[:10]))
    ideal = sorted([relevance(v, c) for c in ranked], reverse=True)  # нормируем на лучший порядок этого же списка кандидатов
    return {"P@10": p10, "P@20": p20, "nDCG@10": dcg, "_ideal_rels": ideal,
            "MRR": next((1 / (i + 1) for i, h in enumerate(hit) if h), 0.0),
            "Recall@50": sum(hit) / all_rel_count if all_rel_count else float("nan")}


def evaluate(vacs, cands, seed, only: list[str] | None = None):
    rng = random.Random(seed)
    no_fsp = dict(ranker.DEFAULT_WEIGHTS)
    no_fsp["fsp"] = 0.0
    s = sum(no_fsp.values())
    no_fsp = {k: v / s for k, v in no_fsp.items()}
    methods = {
        "Случайный (в специализации)": lambda v: rank_random(v, cands, rng),
        "Ключевые слова резюме": lambda v: rank_keyword(v, cands, rng),
        "Только категория по тесту": lambda v: rank_category(v, cands, rng),
        "Наш ранжировщик без ФСП": lambda v: rank_ours(v, cands, no_fsp),
        "Наш до экспертизы (промежуточная сдача)": lambda v: rank_v1(v, cands),
        "Наш без пограничных кандидатов": lambda v: rank_ours(v, cands, borderline=False),
        "Наш ранжировщик (полный)": lambda v: rank_ours(v, cands),
        "Наш + смежные категории": lambda v: rank_ours(v, cands, None, True),
    }
    if only:
        methods = {m: f for m, f in methods.items() if m in only}
    res = {m: [] for m in methods}
    for v in vacs:
        all_rels = [relevance(v, c) for c in cands]
        n_rel = sum(1 for r in all_rels if r >= 2)
        ideal_dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(sorted(all_rels, reverse=True)[:10]))
        for m, f in methods.items():
            mm = metrics(f(v), v, n_rel)
            mm["nDCG@10"] = mm["nDCG@10"] / ideal_dcg if ideal_dcg else float("nan")
            mm.pop("_ideal_rels")
            res[m].append(mm)
    boot = np.random.default_rng(seed)
    out = {}
    for m, rows in res.items():
        out[m] = {}
        for k in ("P@10", "P@20", "nDCG@10", "MRR", "Recall@50"):
            vals = np.array([r[k] for r in rows], dtype=float)
            vals = vals[~np.isnan(vals)]
            bs = [boot.choice(vals, len(vals)).mean() for _ in range(1000)]
            out[m][k] = {"mean": round(float(vals.mean()), 3), "ci95": [round(float(np.percentile(bs, 2.5)), 3),
                                                                     round(float(np.percentile(bs, 97.5)), 3)]}
    return out


def fsp_lift(vacs, cands) -> dict:
    """Насколько один результат ФСП поднимает кандидата в выдаче под конкретную вакансию.

    Берём кандидата из середины выдачи без истории ФСП и добавляем ему ровно одно достижение: (а) призёр
    всероссийских соревнований со стеком из обязательных навыков вакансии; (б) тот же результат со стеком,
    не связанным с вакансией; (в) середина таблицы регионального этапа со стеком вакансии. Сравниваем, на
    сколько позиций он поднялся, у текущего ранжировщика и у версии до экспертизы."""
    from copy import copy
    other_stack = {"backend": ["react", "typescript"], "frontend": ["go", "postgresql"], "data_science": ["react", "nodejs"],
                   "devops": ["react", "typescript"], "qa": ["pytorch", "pandas"]}
    date = (NOW - timedelta(days=60)).date().isoformat()

    def ach(v, level, place, total, stack):
        a = {"id": "lift", "event_name": "Соревнования (проверка)", "discipline": "product", "discipline_name": "product",
             "level": level, "level_name": level, "format": "team", "participants_total": total, "place": place,
             "date": date, "stack": stack, "verified": True}
        return {"items": [a], "summary": fsp_scoring.summarize([a], None, NOW.date()), "participant": {}}

    variants = {
        "призёр всероссийских, стек вакансии": lambda v: ach(v, "national", 2, 120, [SKILL_TAG[x] for x in v.must_skills if x in SKILL_TAG] or ["python"]),
        "призёр всероссийских, чужой стек": lambda v: ach(v, "national", 2, 120, other_stack[v.specialization]),
        "середина регионального этапа, стек вакансии": lambda v: ach(v, "regional", 20, 40, [SKILL_TAG[x] for x in v.must_skills if x in SKILL_TAG] or ["python"]),
    }
    out = {k: {"сейчас": [], "до экспертизы": []} for k in variants}
    start, size = [], []
    for v in vacs:
        if not any(x in SKILL_TAG for x in v.must_skills):
            continue
        for label, mod in (("сейчас", ranker), ("до экспертизы", ranker_v1)):
            req = mod.Requirement.from_obj(v)
            base = [r["candidate"] for r in mod.rank(req, cands)]
            pool = [c for c in base if not c.fsp_data and c.grade == v.grade]
            if len(pool) < 9:
                continue
            c0 = pool[len(pool) // 2]
            pos0 = base.index(c0)
            if label == "сейчас":
                start.append(pos0 + 1)
                size.append(len(base))
            for name, make in variants.items():
                c1 = copy(c0)
                c1.fsp_data = make(v)
                ranked = [r["candidate"] for r in mod.rank(req, [c for c in cands if c is not c0] + [c1])]
                out[name][label].append(pos0 - ranked.index(c1))
    res = {k: {lbl: round(float(np.mean(x)), 1) if x else None for lbl, x in d.items()} | {"n": len(d["сейчас"])}
           for k, d in out.items()}
    return {"variants": res, "start_position": round(float(np.mean(start)), 1), "list_size": round(float(np.mean(size)), 1)}


def ltr_experiment(vacs, cands, seed):
    """Скрытая модель решения кандидата: деньги и стек важнее, чем считают эксперты. Обучаемся на исходах
    приглашений половины вакансий, проверяем ожидаемую долю принятых в топ-10 на другой половине."""
    rng = np.random.default_rng(seed)

    def p_accept(f):
        z = 3.2 * f["salary_fit"] + 2.0 * f["skill_fit"] + 1.2 * f["format_fit"] + 0.6 * f["grade_fit"] - 4.0
        return 1 / (1 + math.exp(-z))

    idx = rng.permutation(len(vacs))
    train_v, test_v = [vacs[i] for i in idx[: len(vacs) // 2]], [vacs[i] for i in idx[len(vacs) // 2:]]
    samples = []
    for v in train_v:
        req = ranker.Requirement.from_obj(v)
        for r in ranker.rank(req, cands)[:30]:
            f = r["features"]
            samples.append((f, 1 if rng.random() < p_accept(f) else 0))
    trained = ltr.train(samples, seed=seed)

    def expected_accept(weights):
        vals, rel = [], []
        for v in test_v:
            req = ranker.Requirement.from_obj(v)
            top = ranker.rank(req, cands, weights)[:10]
            if top:
                vals.append(np.mean([p_accept(r["features"]) for r in top]))
                rel.append(np.mean([relevance(v, r["candidate"]) >= 2 for r in top]))
        return float(np.mean(vals)), float(np.mean(rel))

    return {"train_samples": trained["n"], "weights_default": ranker.DEFAULT_WEIGHTS, "weights_learned": trained["weights"],
            "auc_holdout_default": trained.get("auc_holdout_default"), "auc_holdout_new": trained.get("auc_holdout_new"),
            "expected_accept_top10_default": round(expected_accept(None)[0], 3),
            "expected_accept_top10_learned": round(expected_accept(trained["weights"])[0], 3),
            "p10_default": round(expected_accept(None)[1], 3), "p10_learned": round(expected_accept(trained["weights"])[1], 3)}


LAV, PLUM, PINK = "#8A83D1", "#5B3A8E", "#FF0053"


def chart(res):
    plt = setup_matplotlib()
    names = list(res)
    p10 = [res[m]["P@10"]["mean"] for m in names]
    nd = [res[m]["nDCG@10"]["mean"] for m in names]
    err = [[res[m]["P@10"]["mean"] - res[m]["P@10"]["ci95"][0] for m in names],
           [res[m]["P@10"]["ci95"][1] - res[m]["P@10"]["mean"] for m in names]]
    fig, ax = plt.subplots(figsize=(7.8, 0.45 * len(names) + 1.0))
    y = np.arange(len(names))
    # один ряд: выделен итоговый ранжировщик, остальное — фон для сравнения; значения подписаны у столбцов
    colors = [PLUM if m == "Наш ранжировщик (полный)" else LAV for m in names]
    ax.barh(y, p10, height=0.62, xerr=err, color=colors, error_kw={"ecolor": PALETTE["ink"], "lw": 1, "capsize": 3})
    for i, (a, b) in enumerate(zip(p10, nd)):
        ax.text(a + err[1][i] + 0.02, i, f"{a:.0%}   nDCG {b:.2f}".replace(".", ","), va="center", fontsize=9,
                color=PALETTE["ink"])
    ax.set_yticks(y, names)
    ax.set_xlim(0, 1.34)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0], ["0", "20%", "40%", "60%", "80%", "100%"])
    ax.set_xlabel("доля релевантных кандидатов в топ-10 (P@10), 95% ДИ")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(OUT / "fig_matching.png")
    plt.close(fig)


def chart_fsp(fsp_sens):
    """P@10 трёх вариантов учёта ФСП при разной связи результатов ФСП с навыками."""
    plt = setup_matplotlib()
    conds = list(fsp_sens)
    methods = [("Наш ранжировщик без ФСП", "сейчас без ФСП", LAV),
               ("Наш до экспертизы (промежуточная сдача)", "до экспертизы", PINK),
               ("Наш ранжировщик (полный)", "сейчас: ФСП под запрос", PLUM)]
    fig, ax = plt.subplots(figsize=(7.6, 3.9))
    h = 0.26
    y = np.arange(len(conds))
    for k, (m, label, col) in enumerate(methods):
        vals = [fsp_sens[c][m]["P@10"] for c in conds]
        ax.barh(y + (k - 1) * (h + 0.02), vals, height=h, color=col, label=label)
        for i, v in enumerate(vals):
            ax.text(v + 0.006, y[i] + (k - 1) * (h + 0.02), f"{v:.1%}".replace(".", ","), va="center", fontsize=8,
                    color=PALETTE["ink"])
    lo = min(fsp_sens[c][m]["P@10"] for c in conds for m, _, _ in methods)
    ax.set_xlim(max(0, lo - 0.08), 1.0)
    ax.set_yticks(y, [c.replace(" (", "\n(").replace("0.8", "0,8").replace("1.6", "1,6") for c in conds], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("P@10 (ось начинается не с нуля)")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.4, -0.22), ncol=3)
    ax.set_title("Связь мест в соревнованиях с навыками", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_fsp_sensitivity.png")
    plt.close(fig)


def chart_sensitivity(sens):
    plt = setup_matplotlib()
    labels = list(sens)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    styles = {"Ключевые слова резюме": (PALETTE["lavender"], "o--"), "Только категория по тесту": (PALETTE["blush"], "s-"),
              "Наш ранжировщик (полный)": (PALETTE["plum"], "o-"), "Случайный (в специализации)": (PALETTE["mist"], "x:")}
    for m, (col, st) in styles.items():
        ax.plot(range(len(labels)), [sens[l][m] for l in labels], st, color=col, lw=2, label=m)
    ax.set_xticks(range(len(labels)), [l.replace(" (", "\n(") for l in labels], fontsize=8)
    ax.set_ylabel("P@10"); ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_title("Чем менее честны резюме, тем важнее подтверждение тестом", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(OUT / "fig_matching_sensitivity.png"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=2000)
    ap.add_argument("--vacancies", type=int, default=60)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    sens = {}
    main_res, main_cands, main_vacs = None, None, None
    for label, noise in RESUME_NOISE.items():
        print(f"Мир «{label}»: кандидаты проходят адаптивный тест…", flush=True)
        cands = make_world(a.candidates, a.seed, noise)
        vacs = make_vacancies(a.vacancies, a.seed, cands)
        res = evaluate(vacs, cands, a.seed)
        sens[label] = {m: res[m]["P@10"]["mean"] for m in res}
        print("  ", sens[label], flush=True)
        main_res, main_cands, main_vacs = res, cands, vacs  # основной — последний (реалистичный)
    # чувствительность к информативности ФСП: тот же мир, разные истории ФСП
    fsp_methods = ["Наш ранжировщик без ФСП", "Наш до экспертизы (промежуточная сдача)", "Наш ранжировщик (полный)"]
    fsp_sens = {}
    for lbl in FSP_NOISE:
        for c in main_cands:
            c.fsp_data = c.fsp_variants[lbl]
        r = evaluate(main_vacs, main_cands, a.seed, only=fsp_methods)
        fsp_sens[lbl] = {m: {"P@10": r[m]["P@10"]["mean"], "nDCG@10": r[m]["nDCG@10"]["mean"]} for m in fsp_methods}
        print("  ФСП", lbl, fsp_sens[lbl], flush=True)
    for c in main_cands:
        c.fsp_data = c.fsp_variants["реалистично (шум 0.8)"]
    lift = fsp_lift(main_vacs, main_cands)
    print("  подъём от одного результата ФСП:", lift, flush=True)
    lt = ltr_experiment(main_vacs, main_cands, a.seed)
    chart(main_res)
    chart_sensitivity(sens)
    chart_fsp(fsp_sens)
    out = {"candidates": len(main_cands), "vacancies": len(main_vacs), "results": main_res, "sensitivity_p10": sens, "ltr": lt,
           "fsp_sensitivity": fsp_sens, "fsp_lift": lift,
           "fsp_share": round(float(np.mean([bool(c.fsp_data) for c in main_cands])), 3),
           "borderline_share": round(float(np.mean([ranker.borderline_up(c)[1] >= ranker.BORDER_P for c in main_cands])), 3),
           "grade_accuracy": round(float(np.mean([c.grade == c.true_grade for c in main_cands])), 3)}
    (OUT / "matching_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
