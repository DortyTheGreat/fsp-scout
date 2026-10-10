"""Подбор конфигурации адаптивного теста на симуляции (обоснование выбранных параметров)."""
import json, random, sys
import numpy as np
from common import blueprint_for, make_pool, new_candidate, passes, run_cat, OUT
from testing_study import claimed_grade, kappa
from app.services.testing import cat

def run(cfg, n=400, seed=7):
    rng = np.random.default_rng(seed); rr = random.Random(seed)
    res = {"acc": [], "agree": [], "len": [], "d1": [], "d2": [], "far": []}
    for spec in ("backend", "frontend", "devops"):
        pool = make_pool(spec, np.random.default_rng(seed + 1)); bp = blueprint_for(spec, pool)
        for _ in range(n):
            c = new_candidate(rng, spec); g = claimed_grade(c.theta, rng)
            d1, l1 = run_cat(c, pool, g, rr, bp, cfg=cfg); d2, _ = run_cat(c, pool, g, rr, bp, cfg=cfg)
            t = passes(c.theta, g)
            res["acc"].append(d1["passed"] == t); res["agree"].append(d1["passed"] == d2["passed"])
            res["len"].append(len(l1)); res["d1"].append(d1["passed"]); res["d2"].append(d2["passed"])
            res["far"].append(abs(c.theta - cat.grade_cut(g)) >= 0.3)
    far = np.array(res["far"]); acc = np.array(res["acc"])
    return {"acc": round(float(acc.mean()), 3), "acc_far": round(float(acc[far].mean()), 3), "agree": round(float(np.mean(res["agree"])), 3),
            "kappa": round(kappa(res["d1"], res["d2"]), 3), "len": round(float(np.mean(res["len"])), 1)}

rows = []
for sel in ("theta", "cut", "mix"):
    for mx in (20, 25):
        for z in (1.645, 1.28):
            cfg = cat.CatConfig(min_items=8, max_items=mx, z=z, select_at=sel)
            r = run(cfg); r.update(select_at=sel, max_items=mx, z=z); rows.append(r); print(r, flush=True)
(OUT / "cat_tuning.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
