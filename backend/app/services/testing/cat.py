"""Адаптивный тест (CAT) — чистая логика без БД, чтобы её можно было симулировать при валидации.

Схема одного шага:
  1. По ответам вычисляется θ̂ и SE (EAP). В оценку входят и ответы недавней попытки того же
     онбординга (не сдал Senior → сразу тест на Middle): это тот же человек в тот же день.
  2. Правило остановки: если интервал θ̂ ± z·SE целиком выше или ниже порога заявленного грейда —
     решение принято (аналог последовательного теста отношения правдоподобия).
  3. Выбор следующего задания:
     • баланс содержания: навык с наибольшим отставанием от «чертежа» теста (blueprint);
     • не больше одного «малоизменчивого» шаблона (меньше 50 различных экземпляров) на тест —
       их ответы проще всего собрать в шпаргалку;
     • среди подходящих — максимум информации Фишера в θ̂;
     • контроль экспозиции «randomesque»: случайный выбор из top-k.
  4. Итог: решение о грейде + статистика согласованности ответов (person-fit lz). Слишком
     «неправдоподобный» паттерн (трудное решено, лёгкое — нет) — признак слитых ответов: результат
     требует подтверждающего теста из шаблонов с неисчерпаемой вариативностью.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from app.services.testing import irt
from app.taxonomy import GRADE_ORDER, grade_cut, grade_from_theta, grade_shift


@dataclass
class ItemParams:
    id: str
    a: float
    b: float
    c: float
    skills: dict[str, float]
    status: str = "active"
    variants: int = 1000  # эмпирическое число различных экземпляров шаблона


@dataclass
class CatConfig:
    min_items: int = 8
    max_items: int = 25
    z: float = 1.645
    top_k: int = 4
    se_floor: float = 0.25            # при такой точности дальше спрашивать бессмысленно
    select_at: str = "theta"          # "theta" | "cut" | "mix" — см. validation/tune_cat.py
    mix_after: int = 4
    low_variety_threshold: int = 50   # шаблон с меньшим числом вариантов считается «малоизменчивым»
    max_low_variety: int = 1
    min_variants: int = 0             # для подтверждающего теста: только шаблоны с вариантами ≥ этого
    aberrant_lz: float = -1.96        # порог person-fit для флага «неправдоподобный паттерн»
    # дотестирование пограничных: после max_items тест продолжается до extend_max_items заданий, пока
    # апостериорная вероятность «выше порога» остаётся в extend_band (решение — почти монетка)
    # Введено после экспертизы: на двух независимых прогонах симуляции даёт +3 п. п. точности у порога ценой
    # +2–2,5 задания в среднем (validation/threshold_options.py). 0 — без дотестирования.
    extend_max_items: int = 35
    extend_band: tuple[float, float] = (0.2, 0.8)


@dataclass
class CatState:
    target_grade: str
    blueprint: dict[str, float]
    used: list[str] = field(default_factory=list)
    obs: list[irt.Obs] = field(default_factory=list)
    prior_obs: list[irt.Obs] = field(default_factory=list)  # ответы недавней связанной попытки
    skill_counts: dict[str, float] = field(default_factory=dict)
    low_variety_used: int = 0

    @property
    def n(self) -> int:
        return len(self.obs)

    def all_obs(self) -> list[irt.Obs]:
        return self.prior_obs + self.obs


def estimate(state: CatState) -> tuple[float, float]:
    return irt.eap(state.all_obs())


def should_stop(state: CatState, cfg: CatConfig) -> bool:
    min_items = max(4, cfg.min_items - len(state.prior_obs) // 2) if state.prior_obs else cfg.min_items
    if state.n < min_items:
        return False
    theta, se = estimate(state)
    cut = grade_cut(state.target_grade)
    if theta - cfg.z * se >= cut or theta + cfg.z * se < cut:
        return True
    if state.n >= cfg.max_items:
        if state.n >= max(cfg.max_items, cfg.extend_max_items):
            return True
        lo, hi = cfg.extend_band
        return not (lo <= irt.prob_above(state.all_obs(), cut) <= hi)
    return se <= cfg.se_floor


def select_next(state: CatState, pool: list[ItemParams], cfg: CatConfig, rng: random.Random) -> ItemParams | None:
    candidates = [p for p in pool if p.id not in state.used and p.status == "active" and p.variants >= cfg.min_variants]
    if state.low_variety_used >= cfg.max_low_variety:
        rich = [p for p in candidates if p.variants >= cfg.low_variety_threshold]
        candidates = rich or candidates
    if not candidates:
        return None
    cut = grade_cut(state.target_grade) if state.target_grade != "intern" else -1.5
    theta = estimate(state)[0] if state.all_obs() else cut
    if cfg.select_at == "cut" or (cfg.select_at == "mix" and state.n >= cfg.mix_after):
        theta = cut
    # баланс содержания: навык с максимальным дефицитом относительно доли в blueprint
    total = sum(state.skill_counts.values()) + 1.0
    deficits = {s: share * total - state.skill_counts.get(s, 0.0) for s, share in state.blueprint.items()}
    for skill, _ in sorted(deficits.items(), key=lambda kv: -kv[1]):
        subset = [p for p in candidates if p.skills.get(skill, 0) >= 0.5]
        if subset:
            candidates = subset
            break
    info = irt.information(theta, np.array([p.a for p in candidates]), np.array([p.b for p in candidates]),
                           np.array([p.c for p in candidates]))
    order = np.argsort(-info, kind="stable")[: cfg.top_k]
    return candidates[int(rng.choice(list(order)))]


def record(state: CatState, item: ItemParams, correct: bool, cfg: CatConfig | None = None) -> None:
    state.used.append(item.id)
    state.obs.append(irt.Obs(item.a, item.b, item.c, 1.0 if correct else 0.0))
    if item.variants < (cfg.low_variety_threshold if cfg else 50):
        state.low_variety_used += 1
    for s, w in item.skills.items():
        state.skill_counts[s] = state.skill_counts.get(s, 0.0) + w


def person_fit(obs: list[irt.Obs], theta: float) -> float:
    """Стандартизованная статистика правдоподобия lz (Drasgow et al., 1985). Сильно отрицательная —
    ответы плохо согласуются с моделью: например, верно решены трудные задания и провалены лёгкие."""
    if len(obs) < 6:
        return 0.0
    l0 = e = v = 0.0
    for o in obs:
        p = float(np.clip(irt.prob(theta, o.a, o.b, o.c), 1e-6, 1 - 1e-6))
        l0 += o.u * math.log(p) + (1 - o.u) * math.log(1 - p)
        e += p * math.log(p) + (1 - p) * math.log(1 - p)
        v += p * (1 - p) * math.log(p / (1 - p)) ** 2
    return (l0 - e) / math.sqrt(v) if v > 0 else 0.0


def decide(state: CatState, cfg: CatConfig) -> dict:
    """Итог теста: пройден ли заявленный грейд и что предложить кандидату дальше."""
    theta, se = estimate(state)
    tg = state.target_grade
    cut = grade_cut(tg)
    lo, hi = theta - cfg.z * se, theta + cfg.z * se
    passed = theta >= cut
    confident = lo >= cut or hi < cut
    lz = person_fit(state.obs, theta)
    result = {
        "theta": round(theta, 3), "se": round(se, 3), "cut": cut, "target_grade": tg,
        "passed": passed, "confident": confident, "p_pass": round(irt.prob_above(state.all_obs(), cut), 3),
        "estimated_grade": grade_from_theta(theta), "n_items": state.n, "n_prior_items": len(state.prior_obs),
        "interval": [round(lo, 3), round(hi, 3)], "person_fit": round(lz, 3),
        "aberrant": bool(passed and lz < cfg.aberrant_lz),
        "upgrade_suggested": None, "lower_grade": None, "can_accept_lower": False,
    }
    nxt = grade_shift(tg, +1)
    if passed and nxt and lo >= grade_cut(nxt) - 0.25 and not result["aberrant"]:
        result["upgrade_suggested"] = nxt  # уверенно справился — предлагаем попробовать грейд выше
    if not passed:
        lower = grade_shift(tg, -1)
        result["lower_grade"] = lower
        # результат уверенно выше порога нижнего грейда — его можно принять без отдельного теста
        if lower and (lower == "intern" or lo >= grade_cut(lower)):
            result["can_accept_lower"] = True
    return result


def default_blueprint(spec_core_skills: list[str], pool: list[ItemParams]) -> dict[str, float]:
    """Равномерный «чертёж» по навыкам специализации, для которых в банке есть задания."""
    have = {s for p in pool for s, w in p.skills.items() if w >= 0.5}
    skills = [s for s in spec_core_skills if s in have]
    return {s: 1.0 / len(skills) for s in skills} if skills else {}


def blueprint_from_requirements(must: list[str], nice: list[str], pool: list[ItemParams],
                                core: list[str]) -> dict[str, float]:
    """Чертёж теста под вакансию: must-навыки весят 2, nice — 1, остальное ядро специализации — 0.5."""
    have = {s for p in pool for s, w in p.skills.items() if w >= 0.5}
    weights: dict[str, float] = {}
    for s in core:
        if s in have:
            weights[s] = 0.5
    for s in nice:
        if s in have:
            weights[s] = max(weights.get(s, 0), 1.0)
    for s in must:
        if s in have:
            weights[s] = 2.0
    total = sum(weights.values()) or 1.0
    return {s: w / total for s, w in weights.items()}


GRADES_TESTABLE = [g for g in GRADE_ORDER if g != "intern"]
