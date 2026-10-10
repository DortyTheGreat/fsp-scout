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
from app.services.matching import ltr, ranker
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
        fsp = {}
        if has_fsp:
            lvl = 1 / (1 + math.exp(-(c.theta + rng.normal(0, 0.6))))
            fsp = {"summary": {"has_history": True, "score_by_spec": {s: round(lvl * (1 if s == spec else 0.6), 3) for s in SPECS},
                               "skills": {"algorithms": {"level": 1 / (1 + math.exp(-c.skill_theta.get("algorithms", c.theta))),
                                                          "evidence": []}} if rng.random() < 0.6 else {},
                               "by_discipline": {}, "total": int(rng.integers(1, 8)), "prizes": 0}}
        fmts = [["remote"], ["hybrid", "remote"], ["office", "hybrid"], ["hybrid"], ["office"]][int(rng.integers(0, 5))]
        cands.append(SimpleNamespace(
            id=i, specialization=spec, grade=assigned, theta=theta_hat, skill_scores=scores, claimed_skills=claimed,
            claimed_grade=g_resume, years=years, fsp_data=fsp, salary_from=int(sal), salary_to=int(sal * 1.2),
            work_formats=fmts, city="Москва", relocation=False,
            last_activity_at=NOW - timedelta(days=int(rng.integers(0, 300))), grade_assigned_at=None,
            true_theta=c.theta, true_skill=c.skill_theta, true_grade=true_g))
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


def rank_ours(v, cands, weights=None, adjacent=None):
    req = ranker.Requirement.from_obj(v)
    return [r["candidate"] for r in ranker.rank(req, cands, weights, include_adjacent=adjacent)]


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


def evaluate(vacs, cands, seed):
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
        "Наш ранжировщик (полный)": lambda v: rank_ours(v, cands),
        "Наш + смежные категории": lambda v: rank_ours(v, cands, None, True),
    }
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


def chart(res):
    plt = setup_matplotlib()
    names = list(res)
    p10 = [res[m]["P@10"]["mean"] for m in names]
    nd = [res[m]["nDCG@10"]["mean"] for m in names]
    err = [[res[m]["P@10"]["mean"] - res[m]["P@10"]["ci95"][0] for m in names],
           [res[m]["P@10"]["ci95"][1] - res[m]["P@10"]["mean"] for m in names]]
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    y = np.arange(len(names))
    colors = [PALETTE["mist"], PALETTE["lavender"], PALETTE["blush"], PALETTE["signal"], PALETTE["plum"], PALETTE["ok"]]
    ax.barh(y, p10, xerr=err, color=colors, error_kw={"ecolor": PALETTE["ink"], "lw": 1, "capsize": 3})
    for i, (a, b) in enumerate(zip(p10, nd)):
        ax.text(a + err[1][i] + 0.02, i, f"{a:.0%}   nDCG {b:.2f}", va="center", fontsize=9)
    ax.set_yticks(y, names)
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("доля релевантных кандидатов в топ-10 (P@10)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(OUT / "fig_matching.png")
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
    lt = ltr_experiment(main_vacs, main_cands, a.seed)
    chart(main_res)
    chart_sensitivity(sens)
    out = {"candidates": len(main_cands), "vacancies": len(main_vacs), "results": main_res, "sensitivity_p10": sens, "ltr": lt,
           "grade_accuracy": round(float(np.mean([c.grade == c.true_grade for c in main_cands])), 3)}
    (OUT / "matching_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
