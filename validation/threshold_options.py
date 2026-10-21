"""Варианты, которые проверяли, чтобы поднять точность решения о грейде у порога (замечание экспертизы).

Все варианты — на одном и том же мире (те же кандидаты и пулы для каждого варианта, тот же код теста):
  • текущая конфигурация: остановка при z = 1,645, 8–25 заданий, выбор задания в θ̂;
  • дотестирование пограничных до 35 заданий: после 25 тест продолжается, пока P(θ ≥ порог) в [0,2; 0,8];
  • строже правило остановки: z = 1,96;
  • выбор заданий у порога после 12-го задания (максимум информации в точке порога, а не в θ̂);
  • уточняющий блок: неуверенное итоговое решение дополняется 10 заданиями у порога, ответы объединяются.
Метрики: точность решения о заявленном грейде у порога (|θ − порог| < 0,3) и вдали, итоговая категория = истинной
(путь как в продукте), число заданий на весь путь.

Запуск: python validation/threshold_options.py [--n 400]   → validation/out/threshold_options.json
"""
from __future__ import annotations

import argparse
import json
import random

import numpy as np

from common import OUT, blueprint_for, make_pool, new_candidate, passes, run_cat, true_grade
from testing_study import claimed_grade
from app.services.testing import cat
from app.taxonomy import SPEC_BY_SLUG, grade_cut


def path(c, pool, bp, g, rr, cfg, block: int):
    d, log, st = run_cat(c, pool, g, rr, bp, cfg=cfg, return_state=True)
    first, items, obs, target = d, len(log), list(st.obs), g
    while not d["passed"]:
        lower = d["lower_grade"]
        if not lower or lower == "intern":
            target = "intern"
            break
        if d["can_accept_lower"]:
            target = lower
            break
        d, log2, st = run_cat(c, pool, lower, rr, bp, cfg=cfg, prior_obs=obs, return_state=True)
        items += len(log2)
        obs += list(st.obs)
        target = lower
    if block and target != "intern" and not d["confident"]:
        bcfg = cat.CatConfig(min_items=block, max_items=block, select_at="cut", z=cfg.z, extend_max_items=0)
        d2, log3, _ = run_cat(c, pool, target, rr, bp, cfg=bcfg, prior_obs=obs, return_state=True)
        items += len(log3)
        if not d2["passed"] and d2.get("lower_grade") and d2["lower_grade"] != "intern":
            target = d2["lower_grade"]
    return first, target, items


def run(name: str, cfg: cat.CatConfig, n: int, seed: int, block: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    rr = random.Random(seed)
    ok, near, exact, items = [], [], [], []
    for spec in SPEC_BY_SLUG:
        pool = make_pool(spec, rng)
        bp = blueprint_for(spec, pool)
        for _ in range(n):
            c = new_candidate(rng, spec)
            g = claimed_grade(c.theta, rng)
            d, final, k = path(c, pool, bp, g, rr, cfg, block)
            ok.append(d["passed"] == passes(c.theta, g))
            near.append(abs(c.theta - grade_cut(g)) < 0.3)
            exact.append(final == true_grade(c.theta))
            items.append(k)
    ok, near = np.array(ok), np.array(near)
    r = {"name": name, "n": len(ok), "near": round(float(ok[near].mean()), 3), "far": round(float(ok[~near].mean()), 3),
         "final_exact": round(float(np.mean(exact)), 3), "items_path": round(float(np.mean(items)), 1)}
    print(r, flush=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="кандидатов на специализацию")
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--only", help="номера вариантов через запятую")
    ap.add_argument("--out", help="имя файла результата в validation/out")
    a = ap.parse_args()
    off = {"extend_max_items": 0}
    variants = [("Как в промежуточной сдаче (z = 1,645, 8–25 заданий)", cat.CatConfig(**off), 0),
                ("Дотестирование пограничных до 35 заданий (включено)", cat.CatConfig(), 0),
                ("Строже остановка: z = 1,96", cat.CatConfig(z=1.96, **off), 0),
                ("Задания у порога после 12-го", cat.CatConfig(select_at="mix", mix_after=12, **off), 0),
                ("Уточняющий блок из 10 заданий", cat.CatConfig(**off), 10),
                ("z = 1,96 и дотестирование до 35", cat.CatConfig(z=1.96), 0)]
    if a.only:
        variants = [variants[int(i)] for i in a.only.split(",")]
    rows = [run(name, cfg, a.n, a.seed, block) for name, cfg, block in variants]
    out = OUT / (a.out or "threshold_options.json")
    out.write_text(json.dumps({"rows": rows, "seed": a.seed}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
