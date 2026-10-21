"""Валидация механики тестирования.

E1. Точность решения о грейде и итоговой категории относительно «истинного» уровня (эталон симуляции).
E2. Повторяемость: один и тот же человек проходит тест дважды (новые задания и экземпляры) — согласие решений.
E3. Операционная характеристика: P(сдал | θ) против идеальной ступеньки.
E4. Дискриминативность: точечно-бисериальная корреляция заданий, AUC разделения слабых и сильных.
E5. Устойчивость к утечкам: атакующему слили ответы на все задания, которые видели 300 предыдущих кандидатов.
    Сравнение с фиксированным набором заданий (единый тест для всех).
E6. Сопоставимость сложности: параметрические шаблоны против «уникальных заданий от нейросети без калибровки»
    и эффект калибровки (MML-EM) по сравнению с экспертными параметрами.
E7. Решения у порога грейда: точность в зависимости от расстояния до порога против «идеального» теста той же
    длины (параметры заданий известны точно, способность одномерна) — это предел для любого теста такой длины;
    итоговая категория с предложением повысить грейд (как в продукте) и доля кандидатов, которых работодатель
    видит в их истинной категории с учётом пометки «на границе грейда».

Запуск: python validation/testing_study.py [--n 600]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict

import numpy as np

from common import (OUT, PALETTE, TrueItem, blueprint_for, instance_of, irt, make_pool, new_candidate, passes,
                    run_cat, setup_matplotlib, true_grade, variant_space)
from app.services.testing import cat
from app.taxonomy import GRADE_ORDER, SPEC_BY_SLUG, grade_cut, grade_from_theta, grade_shift

SPECS = list(SPEC_BY_SLUG)
TESTABLE = ["junior", "middle", "senior"]


def kappa(a: list[bool], b: list[bool]) -> float:
    a, b = np.array(a), np.array(b)
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def auc(scores, labels) -> float:
    s, y = np.asarray(scores), np.asarray(labels).astype(bool)
    pos, neg = s[y], s[~y]
    return float(((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean()))


def claimed_grade(theta: float, rng: np.random.Generator) -> str:
    g = grade_from_theta(theta + rng.normal(0.25, 0.5))  # люди склонны себя немного переоценивать
    return "junior" if g == "intern" else g


def full_path(cand, pool, bp, claimed, rr) -> tuple[str | None, int, int]:
    """Путь кандидата как в продукте: тест на заявленный грейд → (принять грейд ниже | тест ниже,
    в котором учитываются и ответы предыдущей попытки)."""
    d, log, st = run_cat(cand, pool, claimed, rr, bp, return_state=True)
    items, tests = len(log), 1
    if d["passed"]:
        return claimed, items, tests
    lower = d["lower_grade"]
    while lower and lower != "intern":
        if d["can_accept_lower"]:
            return lower, items, tests
        d, log, st = run_cat(cand, pool, lower, rr, bp, prior_obs=st.obs, return_state=True)
        items += len(log)
        tests += 1
        if d["passed"]:
            return lower, items, tests
        lower = d["lower_grade"]
    return "intern", items, tests


def e1_e2(n: int, seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    per_spec, logs_all, rows = {}, [], []
    for spec in SPECS:
        pool = make_pool(spec, rng)
        bp = blueprint_for(spec, pool)
        res = defaultdict(list)
        for _ in range(n):
            c = new_candidate(rng, spec)
            g = claimed_grade(c.theta, rng)
            d1, log1 = run_cat(c, pool, g, rr, bp)
            d2, _ = run_cat(c, pool, g, rr, bp)
            truth = passes(c.theta, g)
            res["truth"].append(truth)
            res["dec1"].append(d1["passed"])
            res["dec2"].append(d2["passed"])
            res["theta"].append(c.theta)
            res["th1"].append(d1["theta"])
            res["th2"].append(d2["theta"])
            res["len"].append(d1["n_items"])
            res["aberrant_honest"].append(d1["aberrant"])
            res["near"].append(abs(c.theta - grade_cut(g)) < 0.3)
            final, items, tests = full_path(c, pool, bp, g, rr)
            final2, _, _ = full_path(c, pool, bp, g, rr)
            res["final_retest"].append(final == final2)
            res["final_exact"].append(final == true_grade(c.theta))
            res["final_within1"].append(abs(GRADE_ORDER.index(final) - GRADE_ORDER.index(true_grade(c.theta))) <= 1)
            res["path_items"].append(items)
            logs_all.append((spec, d1["theta"], c.theta, log1))
            rows.append((spec, c.theta, g, d1["passed"], d1["theta"]))
        t, d1, d2 = np.array(res["truth"]), np.array(res["dec1"]), np.array(res["dec2"])
        th, th1, th2 = np.array(res["theta"]), np.array(res["th1"]), np.array(res["th2"])
        near = np.array(res["near"])
        per_spec[spec] = {
            "n": n, "pool": len(pool),
            "decision_accuracy": round(float((t == d1).mean()), 3),
            "decision_accuracy_far_from_cut": round(float((t == d1)[~near].mean()), 3),
            "decision_accuracy_near_cut": round(float((t == d1)[near].mean()), 3),
            "false_pass": round(float((d1 & ~t).sum() / max(1, (~t).sum())), 3),
            "false_fail": round(float((~d1 & t).sum() / max(1, t.sum())), 3),
            "retest_agreement": round(float((d1 == d2).mean()), 3),
            "retest_kappa": round(kappa(list(d1), list(d2)), 3),
            "theta_corr": round(float(np.corrcoef(th, th1)[0, 1]), 3),
            "theta_rmse": round(float(np.sqrt(((th - th1) ** 2).mean())), 3),
            "retest_theta_corr": round(float(np.corrcoef(th1, th2)[0, 1]), 3),
            "mean_len": round(float(np.mean(res["len"])), 1),
            "p90_len": int(np.percentile(res["len"], 90)),
            "final_category_exact": round(float(np.mean(res["final_exact"])), 3),
            "final_category_retest_agreement": round(float(np.mean(res["final_retest"])), 3),
            "honest_flagged_share": round(float(np.mean(res["aberrant_honest"])), 3),
            "final_category_within1": round(float(np.mean(res["final_within1"])), 3),
            "mean_items_full_path": round(float(np.mean(res["path_items"])), 1),
            "auc_weak_vs_strong": round(auc(th1, t), 3),
        }
        print(f"  E1/E2 {spec}: {per_spec[spec]}")
    return per_spec, {"logs": logs_all, "rows": rows}


def summary(per_spec: dict) -> dict:
    keys = [k for k in next(iter(per_spec.values())) if k not in ("n", "pool")]
    return {k: round(float(np.mean([v[k] for v in per_spec.values()])), 3) for k in keys}


def e3_oc(seed: int, reps: int = 150) -> dict:
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    pool = make_pool("backend", rng)
    bp = blueprint_for("backend", pool)
    grid = np.round(np.arange(-1.2, 2.61, 0.2), 2)
    out = {}
    for target in ("middle", "senior"):
        curve = []
        for th in grid:
            ok = sum(run_cat(new_candidate(rng, "backend", float(th)), pool, target, rr, bp)[0]["passed"] for _ in range(reps))
            curve.append(ok / reps)
        out[target] = {"theta": grid.tolist(), "p_pass": curve}
    return out


def e4_discrimination(logs) -> dict:
    by_item = defaultdict(list)
    for spec, th_hat, th_true, log in logs:
        for tid, _, correct in log:
            by_item[tid].append((th_hat, 1.0 if correct else 0.0))
    pb = {}
    for tid, xs in by_item.items():
        if len(xs) < 30:
            continue
        a = np.array(xs)
        if a[:, 1].std() == 0:
            continue
        pb[tid] = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    vals = np.array(list(pb.values()))
    return {"items_evaluated": len(pb), "point_biserial_median": round(float(np.median(vals)), 3),
            "share_above_0_2": round(float((vals > 0.2).mean()), 3), "share_above_0_3": round(float((vals > 0.3).mean()), 3),
            "weakest": sorted(pb.items(), key=lambda kv: kv[1])[:5]}


def e5_leakage(logs, seed: int, n_attackers: int = 400, dump_size: int = 300) -> dict:
    """Атака «слив»: у атакующего есть ответы на все экземпляры, которые видели dump_size предыдущих кандидатов."""
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    pool = make_pool("backend", rng)
    bp = blueprint_for("backend", pool)
    # 1) платформа работает: dump_size честных кандидатов проходят тесты, система ведёт журнал показанных
    #    экземпляров (shown) и выдаёт свежие. 2) все их задания с ответами слиты в общую базу.
    shown: dict = {}
    backend_logs = []
    for _ in range(dump_size):
        c = new_candidate(rng, "backend")
        _, log = run_cat(c, pool, claimed_grade(c.theta, rng), rr, bp, shown=shown)
        backend_logs.append(("backend", 0, c.theta, log))
    dump = {k for _, _, _, log in backend_logs for _, k, _ in log}
    target, gap = "middle", 0.6  # слабый кандидат: истинный уровень на 0.6 ниже порога Middle
    th_weak = grade_cut(target) - gap

    def leak_override(item: TrueItem, inst_key):
        return True if inst_key in dump else None

    confirm_cfg = cat.CatConfig(min_variants=50, min_items=6, max_items=15, extend_max_items=0)
    no_cap = cat.CatConfig(max_low_variety=99)  # без ограничения малоизменчивых шаблонов и без журнала показов
    stats = {}
    for name, override, cfg in (("no_leak", None, None), ("leak_no_defense", leak_override, no_cap),
                                ("leak", leak_override, None)):
        passed, eff_passed, flagged, hits, total, th_hat = 0, 0, 0, 0, 0, []
        for _ in range(n_attackers):
            c = new_candidate(rng, "backend", th_weak)
            d, log = run_cat(c, pool, target, rr, bp, cfg=cfg, answer_override=override,
                             shown=None if name == "leak_no_defense" else shown)
            passed += d["passed"]
            th_hat.append(d["theta"])
            hits += sum(1 for _, k, _ in log if k in dump)
            total += len(log)
            ok = d["passed"]
            if name != "leak_no_defense" and d["aberrant"]:
                flagged += 1
                dc, _ = run_cat(c, pool, target, rr, bp, cfg=confirm_cfg, answer_override=override, shown=shown)
                ok = dc["passed"]
            eff_passed += ok
        stats[name] = {"pass_rate_raw": round(passed / n_attackers, 3),
                       "pass_rate": round(eff_passed / n_attackers, 3),
                       "flagged_share": round(flagged / n_attackers, 3),
                       "mean_theta_hat": round(float(np.mean(th_hat)), 3), "dump_hit_rate": round(hits / total, 3)}

    # Базовая линия: единый фиксированный тест (15 заданий, максимально информативных у порога), без вариантов
    params = [p.params() for p in pool]
    form = sorted(pool, key=lambda p: -float(irt.information(grade_cut(target), p.a_known, p.b_known, p.c)))[:15]
    static = {}
    for name, leaked in (("no_leak", False), ("leak", True)):
        passed, th_hat = 0, []
        for _ in range(n_attackers):
            c = new_candidate(rng, "backend", th_weak)
            obs = []
            for it in form:
                if leaked:
                    u = 1.0
                else:
                    p = float(irt.prob(c.ability_for(it.skills), it.a_true, it.b_true, it.c))
                    u = 1.0 if rr.random() < p else 0.0
                obs.append(irt.Obs(it.a_known, it.b_known, it.c, u))
            th, _ = irt.eap(obs)
            passed += th >= grade_cut(target)
            th_hat.append(th)
        static[name] = {"pass_rate": round(passed / n_attackers, 3), "mean_theta_hat": round(float(np.mean(th_hat)), 3)}

    # Перекрытие тестов двух случайных кандидатов
    tmpl_ov, inst_ov = [], []
    bl = [l[3] for l in backend_logs]
    for _ in range(2000):
        a, b = rr.sample(bl, 2)
        ta, tb = {x[0] for x in a}, {x[0] for x in b}
        ia, ib = {x[1] for x in a}, {x[1] for x in b}
        tmpl_ov.append(len(ta & tb) / max(1, len(ta)))
        inst_ov.append(len(ia & ib) / max(1, len(ia)))
    vs = {p.id: variant_space(p.id) for p in pool}
    _ = params
    return {"target": target, "attacker_theta": th_weak, "dump_candidates": len(backend_logs), "dump_instances": len(dump),
            "ours": stats, "static_form": static,
            "template_overlap_mean": round(float(np.mean(tmpl_ov)), 3), "instance_overlap_mean": round(float(np.mean(inst_ov)), 4),
            "variant_space_median": int(np.median(list(vs.values()))),
            "templates_with_lt_20_variants": sum(1 for v in vs.values() if v < 20), "templates_total": len(vs)}


def e6_comparability(seed: int, n: int = 500) -> dict:
    """Сопоставимость сложности и эффект калибровки на пуле backend."""
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    pool = make_pool("backend", rng)
    bp = blueprint_for("backend", pool)

    def study(pool_known: list[TrueItem], instance_sd: float, label: str) -> dict:
        r = np.random.default_rng(seed + 1)
        acc, agree, corr_t, corr_h = [], [], [], []
        for _ in range(n):
            c = new_candidate(r, "backend")
            g = claimed_grade(c.theta, r)
            d1, _ = run_cat(c, pool_known, g, rr, bp, instance_sd=instance_sd)
            d2, _ = run_cat(c, pool_known, g, rr, bp, instance_sd=instance_sd)
            acc.append(d1["passed"] == passes(c.theta, g))
            agree.append(d1["passed"] == d2["passed"])
            corr_t.append(c.theta)
            corr_h.append(d1["theta"])
        return {"label": label, "decision_accuracy": round(float(np.mean(acc)), 3),
                "retest_agreement": round(float(np.mean(agree)), 3),
                "theta_corr": round(float(np.corrcoef(corr_t, corr_h)[0, 1]), 3)}

    # 1) калибровка: собираем разреженную матрицу ответов адаптивных тестов и оцениваем (a, b) методом MML-EM
    ids = [p.id for p in pool]
    idx = {t: i for i, t in enumerate(ids)}
    rows = []
    r = np.random.default_rng(seed + 2)
    for _ in range(3000):
        c = new_candidate(r, "backend")
        _, log = run_cat(c, pool, claimed_grade(c.theta, r), rr, bp)
        row = np.full(len(ids), np.nan)
        for tid, _, u in log:
            row[idx[tid]] = 1.0 if u else 0.0
        # претест: 3 случайных незачётных задания на кандидата — делают матрицу менее зависимой от выбора CAT
        for p in r.choice(pool, 3, replace=False):
            if np.isnan(row[idx[p.id]]):
                pr = float(irt.prob(c.ability_for(p.skills), p.a_true, p.b_true, p.c))
                row[idx[p.id]] = 1.0 if r.random() < pr else 0.0
        rows.append(row)
    R = np.array(rows)
    c_vec = np.array([p.c for p in pool])
    a_est, b_est = irt.calibrate(R, c_vec, a0=np.array([p.a_known for p in pool]), b0=np.array([p.b_known for p in pool]))
    b_true = np.array([p.b_true for p in pool])
    b_known = np.array([p.b_known for p in pool])
    a_true = np.array([p.a_true for p in pool])
    calibrated = [TrueItem(p.id, p.skills, p.a_true, p.b_true, p.c, float(a_est[i]), float(b_est[i])) for i, p in enumerate(pool)]
    oracle = [TrueItem(p.id, p.skills, p.a_true, p.b_true, p.c, p.a_true, p.b_true) for p in pool]

    # 2) «уникальные задания от нейросети без калибровки»: трудность каждого экземпляра заметно гуляет
    res = [study(pool, 0.12, "Параметрические шаблоны, экспертные параметры"),
           study(calibrated, 0.12, "Параметрические шаблоны после калибровки (MML-EM)"),
           study(oracle, 0.12, "Идеально известные параметры (верхняя граница)"),
           study(pool, 0.70, "Уникальные задания без калибровки (разброс трудности 0.7)")]
    return {"studies": res,
            "calibration": {"b_corr_expert": round(float(np.corrcoef(b_known, b_true)[0, 1]), 3),
                            "b_corr_calibrated": round(float(np.corrcoef(b_est, b_true)[0, 1]), 3),
                            "b_rmse_expert": round(float(np.sqrt(((b_known - b_true) ** 2).mean())), 3),
                            "b_rmse_calibrated": round(float(np.sqrt(((b_est - b_true) ** 2).mean())), 3),
                            "a_corr_calibrated": round(float(np.corrcoef(a_est, a_true)[0, 1]), 3),
                            "n_respondents": len(R), "responses": int((~np.isnan(R)).sum())},
            "_scatter": {"b_true": b_true.tolist(), "b_expert": b_known.tolist(), "b_cal": b_est.tolist()}}


DIST_BINS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.5), (0.5, 0.8), (0.8, 9.0)]


def _path_with_obs(cand, pool, bp, claimed, rr, take_upgrade: bool):
    """Путь как в продукте, плюс (take_upgrade) тест на грейд выше, если система его предложила."""
    d, log, st = run_cat(cand, pool, claimed, rr, bp, return_state=True)
    obs, target = list(st.obs), claimed
    if d["passed"]:
        while take_upgrade and d.get("upgrade_suggested"):
            nxt = d["upgrade_suggested"]
            d2, _, st2 = run_cat(cand, pool, nxt, rr, bp, return_state=True)
            if not d2["passed"]:
                break
            d, obs, target = d2, list(st2.obs), nxt
        return target, d
    while True:
        lower = d["lower_grade"]
        if not lower or lower == "intern":
            return "intern", d
        if d["can_accept_lower"]:
            return lower, d
        d, _, st = run_cat(cand, pool, lower, rr, bp, prior_obs=obs, return_state=True)
        obs = obs + list(st.obs)
        if d["passed"]:
            return lower, d


def e7_borderline(seed: int, n: int = 400) -> dict:
    from types import SimpleNamespace
    from app.services.matching import ranker
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    rows = []
    for spec in SPECS:
        pool = make_pool(spec, rng)
        oracle = [TrueItem(p.id, p.skills, p.a_true, p.b_true, p.c, p.a_true, p.b_true) for p in pool]
        bp = blueprint_for(spec, pool)
        for _ in range(n):
            c = new_candidate(rng, spec)
            ideal = new_candidate(rng, spec, theta=c.theta, skill_sd=0.0)  # одномерная способность
            g = claimed_grade(c.theta, rng)
            d1, _ = run_cat(c, pool, g, rr, bp)
            di, _ = run_cat(ideal, oracle, g, rr, bp)
            final, dfin = _path_with_obs(c, pool, bp, g, rr, take_upgrade=False)
            final_up, _ = _path_with_obs(c, pool, bp, g, rr, take_upgrade=True)
            tg = true_grade(c.theta)
            vis = final == tg
            if not vis and final != "intern":
                nxt, p_up = ranker.borderline_up(SimpleNamespace(grade=final, theta=dfin["theta"], theta_se=dfin["se"]))
                vis = nxt == tg and p_up >= ranker.BORDER_P
                border = p_up >= ranker.BORDER_P
            else:
                border = final != "intern" and ranker.borderline_up(
                    SimpleNamespace(grade=final, theta=dfin["theta"], theta_se=dfin["se"]))[1] >= ranker.BORDER_P
            rows.append({"dist": abs(c.theta - grade_cut(g)), "ok": d1["passed"] == passes(c.theta, g),
                         "ok_ideal": di["passed"] == passes(c.theta, g), "len": d1["n_items"], "len_ideal": di["n_items"],
                         "exact": final == tg, "exact_up": final_up == tg, "visible": vis, "border": border})
    col = {k: np.array([r[k] for r in rows], dtype=float) for k in rows[0]}
    dist, ok, ok_i = col["dist"], col["ok"].astype(bool), col["ok_ideal"].astype(bool)
    bins = []
    for lo, hi in DIST_BINS:
        m = (dist >= lo) & (dist < hi)
        bins.append({"lo": lo, "hi": hi if hi < 9 else None, "n": int(m.sum()), "ours": round(float(ok[m].mean()), 3),
                     "ideal": round(float(ok_i[m].mean()), 3)})
    near = dist < 0.3
    return {"bins": bins,
            "near_ours": round(float(ok[near].mean()), 3), "near_ideal": round(float(ok_i[near].mean()), 3),
            "far_ours": round(float(ok[~near].mean()), 3), "far_ideal": round(float(ok_i[~near].mean()), 3),
            "beyond_05_ours": round(float(ok[dist >= 0.5].mean()), 3),
            "near_share": round(float(near.mean()), 3),
            "mean_len": round(float(col["len"].mean()), 1), "mean_len_ideal": round(float(col["len_ideal"].mean()), 1),
            "final_exact": round(float(col["exact"].mean()), 3), "final_exact_with_upgrade": round(float(col["exact_up"].mean()), 3),
            "visible_in_true_category": round(float(col["visible"].mean()), 3),
            "borderline_share": round(float(col["border"].mean()), 3), "n": len(rows)}


def chart_distance(e7: dict):
    plt = setup_matplotlib()
    bins = e7["bins"]
    labels = [f"{b['lo']:.1f}–{b['hi']:.1f}".replace(".", ",") if b["hi"] else f"≥ {b['lo']:.1f}".replace(".", ",")
              for b in bins]
    x = np.arange(len(bins))
    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    ax.axvspan(-0.4, 2.5, color="#F1EFF8", zorder=0)
    ax.text(1.0, 0.43, "у порога (|θ − порог| < 0,3)", ha="center", fontsize=8, color=PALETTE["ink"])
    ax.axhline(0.5, color="#C9D2D0", lw=1, ls=":", zorder=1)
    ax.plot(x, [b["ideal"] for b in bins], "o--", color="#8A83D1", lw=2, ms=6, label="идеальный тест той же длины")
    ax.plot(x, [b["ours"] for b in bins], "o-", color="#5B3A8E", lw=2, ms=6, label="наш тест")
    for i, b in enumerate(bins):
        ax.text(i, b["ours"] - 0.07, f"{b['ours']:.0%}", ha="center", fontsize=8, color=PALETTE["ink"])
    ax.set_xticks(x, labels)
    ax.set_xlabel("расстояние истинного уровня до порога грейда, θ")
    ax.set_ylabel("доля верных решений")
    ax.set_ylim(0.38, 1.03)
    ax.set_xlim(-0.4, len(bins) - 0.6)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_accuracy_distance.png")
    plt.close(fig)


def charts(oc, e1rows, leak, e6):
    plt = setup_matplotlib()
    # OC-кривые
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for target, color in (("middle", PALETTE["plum"]), ("senior", PALETTE["signal"])):
        d = oc[target]
        ax.plot(d["theta"], d["p_pass"], "-o", ms=3, color=color, label=f"тест на {target.capitalize()}")
        cut = grade_cut(target)
        ax.plot([min(d["theta"]), cut, cut, max(d["theta"])], [0, 0, 1, 1], "--", color=color, alpha=0.35, lw=1)
    ax.set_xlabel("истинный уровень θ"); ax.set_ylabel("вероятность сдать")
    ax.legend(frameon=False); ax.set_title("Операционные характеристики теста (пунктир — идеал)", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(OUT / "fig_oc.png"); plt.close(fig)
    # θ̂ против θ
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    rows = e1rows[:1500]
    th = np.array([r[1] for r in rows]); hat = np.array([r[4] for r in rows]); ok = np.array([r[3] == passes(r[1], r[2]) for r in rows])
    ax.scatter(th[ok], hat[ok], s=6, color=PALETTE["lavender"], alpha=0.6, label="решение о грейде верное")
    ax.scatter(th[~ok], hat[~ok], s=9, color=PALETTE["signal"], alpha=0.9, label="ошибка решения")
    ax.plot([-3, 3], [-3, 3], color=PALETTE["plum"], lw=1)
    for g in ("junior", "middle", "senior"):
        ax.axvline(grade_cut(g), color=PALETTE["mist"], lw=1, zorder=0)
    ax.set_xlabel("истинный θ"); ax.set_ylabel("оценка теста θ̂"); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "fig_recovery.png"); plt.close(fig)
    # утечки
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    labels = ["Единый тест\nбез утечки", "Единый тест\nответы слиты", "Наш тест\nбез утечки",
              "Наш тест, слив,\nбез защит", "Наш тест, слив,\nс защитами"]
    vals = [leak["static_form"]["no_leak"]["pass_rate"], leak["static_form"]["leak"]["pass_rate"],
            leak["ours"]["no_leak"]["pass_rate"], leak["ours"]["leak_no_defense"]["pass_rate"], leak["ours"]["leak"]["pass_rate"]]
    bars = ax.bar(labels, vals, color=[PALETTE["mist"], PALETTE["signal"], PALETTE["lavender"], PALETTE["blush"], PALETTE["plum"]])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.0%}", ha="center", fontsize=9)
    ax.set_ylim(0, 1.1); ax.set_ylabel("доля сдавших Middle")
    ax.set_title("Слабый кандидат (θ на 0.6 ниже порога) со слитыми ответами", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(OUT / "fig_leak.png"); plt.close(fig)
    # калибровка
    sc = e6["_scatter"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.scatter(sc["b_true"], sc["b_expert"], s=14, color=PALETTE["lavender"], label="экспертная оценка")
    ax.scatter(sc["b_true"], sc["b_cal"], s=14, color=PALETTE["signal"], label="после калибровки")
    ax.plot([-2.5, 2.5], [-2.5, 2.5], color=PALETTE["plum"], lw=1)
    ax.set_xlabel("истинная трудность b"); ax.set_ylabel("оценка b"); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "fig_calibration.png"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600, help="кандидатов на специализацию")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    t0 = time.time()
    print("E1/E2: точность и повторяемость…")
    per_spec, extra = e1_e2(a.n, a.seed)
    print("E3: операционные характеристики…")
    oc = e3_oc(a.seed)
    print("E4: дискриминативность…")
    disc = e4_discrimination(extra["logs"])
    print("E5: утечки…")
    leak = e5_leakage(extra["logs"], a.seed)
    print("E6: сопоставимость и калибровка…")
    e6 = e6_comparability(a.seed)
    print("E7: решения у порога…")
    e7 = e7_borderline(a.seed)
    charts(oc, extra["rows"], leak, e6)
    chart_distance(e7)
    result = {"per_spec": per_spec, "overall": summary(per_spec), "oc": oc, "discrimination": disc, "leakage": leak,
              "borderline": e7,
              "comparability": {k: v for k, v in e6.items() if not k.startswith("_")}, "seconds": round(time.time() - t0)}
    (OUT / "testing_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({k: result[k] for k in ("overall", "discrimination", "leakage", "comparability", "borderline")},
                     ensure_ascii=False, indent=1))
    _ = (GRADE_ORDER, grade_shift, cat)


if __name__ == "__main__":
    main()
