"""Общие функции валидации: банк заданий, симуляция кандидатов и прохождения адаптивного теста.

Используется ТОТ ЖЕ код, что в продукте (app.services.testing.cat / irt, банк шаблонов),
меняются только «ответы»: вероятность верного ответа задаётся моделью 3PL с ИСТИННЫМИ параметрами,
которые отличаются от параметров, известных системе (экспертная оценка ≠ реальность).
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.services.testing import cat, irt  # noqa: E402
from app.services.testing.bank import TEMPLATES  # noqa: E402
from app.taxonomy import SPEC_BY_SLUG, grade_cut, grade_from_theta  # noqa: E402

OUT = ROOT / "validation" / "out"
OUT.mkdir(parents=True, exist_ok=True)

PALETTE = {"plum": "#2D1451", "signal": "#FF0053", "lavender": "#8A83D1", "mist": "#E4EAE9", "ink": "#1C1D22",
           "blush": "#FFD6E3", "ok": "#13795B"}


@dataclass
class TrueItem:
    """Шаблон с «истинными» параметрами (их система не знает) и известными системе (экспертными/калиброванными)."""
    id: str
    skills: dict
    a_true: float
    b_true: float
    c: float
    a_known: float
    b_known: float

    def params(self) -> cat.ItemParams:
        return cat.ItemParams(self.id, self.a_known, self.b_known, self.c, self.skills, variants=variant_space(self.id))


def make_pool(spec: str, rng: np.random.Generator, a_noise: float = 0.25, b_noise: float = 0.35) -> list[TrueItem]:
    """Истинные параметры = экспертные с ошибкой: эксперт систематически не знает точную трудность шаблона."""
    pool = []
    for t in TEMPLATES.values():
        if spec not in t.specs:
            continue
        a_true = float(t.a * np.exp(rng.normal(0, a_noise)))
        b_true = float(t.b + rng.normal(0, b_noise))
        pool.append(TrueItem(t.id, t.skills, a_true, b_true, t.c, t.a, t.b))
    return pool


@dataclass
class SimCandidate:
    theta: float
    skill_theta: dict = field(default_factory=dict)

    def ability_for(self, skills: dict) -> float:
        if not skills:
            return self.theta
        num = sum(w * self.skill_theta.get(s, self.theta) for s, w in skills.items())
        return num / sum(skills.values())


def new_candidate(rng: np.random.Generator, spec: str, theta: float | None = None, skill_sd: float = 0.45) -> SimCandidate:
    th = float(rng.normal(0.15, 1.0)) if theta is None else theta
    return SimCandidate(th, {s: th + float(rng.normal(0, skill_sd)) for s in SPEC_BY_SLUG[spec].core_skills})


def blueprint_for(spec: str, pool: list[TrueItem]) -> dict:
    return cat.default_blueprint(list(SPEC_BY_SLUG[spec].core_skills), [p.params() for p in pool])


def run_cat(cand: SimCandidate, pool: list[TrueItem], target: str, rng: random.Random, blueprint: dict,
            cfg: cat.CatConfig | None = None, instance_sd: float = 0.12, answer_override=None,
            prior_obs: list | None = None, return_state: bool = False, shown: dict | None = None,
            fresh_tries: int = 12):
    """Проходит адаптивный тест. instance_sd — разброс трудности между экземплярами одного шаблона
    (изоморфные варианты не идеально равны). answer_override(item, instance_key) → bool|None — для атак."""
    cfg = cfg or cat.CatConfig()
    by_id = {p.id: p for p in pool}
    params = [p.params() for p in pool]
    st = cat.CatState(target_grade=target, blueprint=blueprint, prior_obs=list(prior_obs or []))
    log = []
    while not cat.should_stop(st, cfg):
        skipped = []
        for _ in range(3 if shown is not None else 1):
            it = cat.select_next(st, params, cfg, rng)
            if it is None:
                break
            ti = by_id[it.id]
            inst_key = (ti.id, instance_of(ti.id, rng.getrandbits(31)))
            if shown is None:
                break
            # как в продукте: экземпляр, который ещё никому не показывали; шаблон без свежих — пропускаем
            reg = shown.setdefault(ti.id, set())
            fresh = inst_key not in reg
            for _ in range(fresh_tries - 1):
                if fresh:
                    break
                inst_key = (ti.id, instance_of(ti.id, rng.getrandbits(31)))
                fresh = inst_key not in reg
            if fresh:
                break
            st.used.append(it.id)
            skipped.append(it.id)
        if it is None:
            break
        for sid in skipped:  # пропущенные шаблоны не засчитываются как показанные
            if sid != it.id and sid in st.used:
                st.used.remove(sid)
        if shown is not None:
            shown.setdefault(ti.id, set()).add(inst_key)
        forced = answer_override(ti, inst_key) if answer_override else None
        if forced is None:
            b_inst = ti.b_true + rng.gauss(0, instance_sd)
            p = float(irt.prob(cand.ability_for(ti.skills), ti.a_true, b_inst, ti.c))
            correct = rng.random() < p
        else:
            correct = forced
        cat.record(st, it, correct, cfg)
        log.append((ti.id, inst_key, correct))
    if return_state:
        return cat.decide(st, cfg), log, st
    return cat.decide(st, cfg), log


_variant_ids: dict[str, list] = {}


def instance_of(tid: str, seed: int, n: int = 1500) -> int:
    """Номер «смыслового» экземпляра: шаблоны с малым числом вариантов дают совпадения — это и моделируем."""
    if tid not in _variant_ids:
        t = TEMPLATES[tid]
        seen, ids = {}, []
        for s in range(n):
            i = t.render(s)
            correct = (i.options[i.answer] if i.fmt == "single" else
                       tuple(sorted(i.options[k] for k in i.answer)) if i.fmt == "multi" else tuple(i.answer))
            key = (i.prompt, i.code, correct)
            seen.setdefault(key, len(seen))
            ids.append(seen[key])
        _variant_ids[tid] = ids
    ids = _variant_ids[tid]
    if len(set(ids)) >= 0.9 * len(ids):
        return seed  # пространство вариантов практически неисчерпаемо: каждый seed — новый экземпляр
    return ids[seed % len(ids)]


def variant_space(tid: str) -> int:
    instance_of(tid, 0)
    return len(set(_variant_ids[tid]))


def true_grade(theta: float) -> str:
    return grade_from_theta(theta)


def passes(theta: float, grade: str) -> bool:
    return theta >= grade_cut(grade)


def setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#C9D2D0",
                         "axes.labelcolor": PALETTE["ink"], "xtick.color": PALETTE["ink"], "ytick.color": PALETTE["ink"],
                         "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 140})
    return plt
