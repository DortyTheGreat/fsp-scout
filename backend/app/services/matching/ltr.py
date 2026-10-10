"""Дообучение весов ранжирования на исходах приглашений (механика обратной связи команды, п. 4.1).

Каждое приглашение хранит вектор факторов в момент отправки. Исход: принято (1) / отклонено (0).
Отказы «сейчас не ищу работу» не несут информации о качестве совпадения и исключаются.
Обучаем логистическую регрессию с L2 на факторах и смешиваем полученную важность с экспертными весами
пропорционально объёму данных — при малом числе исходов модель почти не отходит от экспертной.
"""
from __future__ import annotations

import numpy as np

from app.services.matching.ranker import DEFAULT_WEIGHTS, FACTORS

# Факторы соответствия работодателю: дообучение на согласиях кандидатов не должно их «выключать»,
# иначе модель научится показывать тех, кто охотно соглашается, а не тех, кто подходит.
FIT_FACTORS = ("skill_fit", "grade_fit", "test_strength", "fsp")
FIT_FLOOR = 0.8  # не ниже 80% экспертного веса


def fit_logreg(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 500, lr: float = 0.5) -> np.ndarray:
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        grad = Xb.T @ (p - y) / n + l2 * np.r_[w[:-1], 0] / n
        w -= lr * grad
    return w


def auc(scores: np.ndarray, y: np.ndarray) -> float:
    pos, neg = scores[y == 1], scores[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def train(samples: list[tuple[dict, int]], prior_strength: float = 60.0, seed: int = 0) -> dict:
    if len(samples) < 10 or len({y for _, y in samples}) < 2:
        return {"weights": dict(DEFAULT_WEIGHTS), "n": len(samples), "note": "мало данных — экспертные веса"}
    rng = np.random.default_rng(seed)
    X = np.array([[f[k] for k in FACTORS] for f, _ in samples], dtype=float)
    y = np.array([lbl for _, lbl in samples], dtype=float)
    idx = rng.permutation(len(y))
    cut = int(len(y) * 0.75)
    tr, te = idx[:cut], idx[cut:]
    w = fit_logreg(X[tr], y[tr])
    coef = np.maximum(w[:-1], 0) + 1e-3          # отрицательный вклад фактора не допускаем (монотонность)
    learned = coef / coef.sum()
    alpha = len(y) / (len(y) + prior_strength)  # доверие к данным растёт с их объёмом
    mixed = {k: (1 - alpha) * DEFAULT_WEIGHTS[k] + alpha * learned[i] for i, k in enumerate(FACTORS)}
    for _ in range(20):  # нормировка с нижней границей для факторов соответствия
        s = sum(mixed.values())
        mixed = {k: v / s for k, v in mixed.items()}
        low = [k for k in FIT_FACTORS if mixed[k] < FIT_FLOOR * DEFAULT_WEIGHTS[k]]
        if not low:
            break
        for k in low:
            mixed[k] = FIT_FLOOR * DEFAULT_WEIGHTS[k]
        free = [k for k in FACTORS if k not in low]
        rest = 1 - sum(mixed[k] for k in low)
        fs = sum(mixed[k] for k in free)
        for k in free:
            mixed[k] = mixed[k] / fs * rest
    mixed = {k: round(v, 4) for k, v in mixed.items()}
    base_auc = auc(X[te] @ np.array([DEFAULT_WEIGHTS[k] for k in FACTORS]), y[te])
    new_auc = auc(X[te] @ np.array([mixed[k] for k in FACTORS]), y[te])
    return {"weights": mixed, "n": len(y), "alpha": round(alpha, 3), "learned": dict(zip(FACTORS, map(float, learned.round(4)))),
            "auc_holdout_default": round(base_auc, 3), "auc_holdout_new": round(new_auc, 3)}
