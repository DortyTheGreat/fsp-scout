"""Математика теории ответа на задание (IRT), трёхпараметрическая логистическая модель (3PL).

    P(верно | θ) = c + (1 − c) / (1 + exp(−a·(θ − b)))

θ — способность кандидата, b — трудность задания (точка на той же шкале), a — дискриминативность
(насколько резко задание отделяет слабых от сильных), c — вероятность угадать.

Оценка θ — EAP (апостериорное среднее) на сетке: устойчива при малом числе ответов и даёт
стандартную ошибку SE, на которой строится правило остановки адаптивного теста.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

GRID = np.linspace(-4.0, 4.0, 161)
PRIOR_MU = 0.0
PRIOR_SD = 1.5  # слабоинформативный априор: не «прижимает» сильных кандидатов к среднему


@dataclass(frozen=True)
class Obs:
    a: float
    b: float
    c: float
    u: float          # 1 — верно, 0 — неверно
    w: float = 1.0    # вес наблюдения (для оценок по навыку)


def prob(theta, a: float, b: float, c: float):
    return c + (1.0 - c) / (1.0 + np.exp(-a * (theta - b)))


def information(theta, a: float, b: float, c: float):
    """Информация Фишера задания 3PL в точке θ."""
    p = prob(theta, a, b, c)
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return (a ** 2) * ((p - c) ** 2 / (1.0 - c) ** 2) * ((1.0 - p) / p)


def posterior(obs: list[Obs], mu: float = PRIOR_MU, sd: float = PRIOR_SD) -> np.ndarray:
    log_post = -0.5 * ((GRID - mu) / sd) ** 2
    for o in obs:
        p = np.clip(prob(GRID, o.a, o.b, o.c), 1e-9, 1 - 1e-9)
        log_post += o.w * (o.u * np.log(p) + (1.0 - o.u) * np.log(1.0 - p))
    log_post -= log_post.max()
    w = np.exp(log_post)
    return w / w.sum()


def eap(obs: list[Obs], mu: float = PRIOR_MU, sd: float = PRIOR_SD) -> tuple[float, float]:
    """Возвращает (θ̂, SE)."""
    w = posterior(obs, mu, sd)
    mean = float((w * GRID).sum())
    var = float((w * (GRID - mean) ** 2).sum())
    return mean, math.sqrt(max(var, 1e-12))


def prob_above(obs: list[Obs], cut: float, mu: float = PRIOR_MU, sd: float = PRIOR_SD) -> float:
    """Апостериорная вероятность того, что θ ≥ cut."""
    w = posterior(obs, mu, sd)
    return float(w[GRID >= cut].sum())


def theta_to_score(theta: float) -> int:
    """Шкала 0–100 для людей: θ=0 → 50, θ=1 → 73, θ=2 → 88."""
    return int(round(100.0 / (1.0 + math.exp(-theta))))


# ------------------------------------------------------------------ калибровка нового задания при известных θ
def fit_item_fixed_theta(thetas: np.ndarray, u: np.ndarray, c: float, a0: float = 1.0, b0: float = 0.0,
                         iters: int = 50) -> tuple[float, float]:
    """Калибровка претест-задания: θ отвечавших известны по зачётным заданиям того же теста,
    подбираем (a, b) методом Ньютона по правдоподобию 3PL с фиксированным c."""
    a, b = a0, b0
    for _ in range(iters):
        z = 1 / (1 + np.exp(-a * (thetas - b)))
        p = np.clip(c + (1 - c) * z, 1e-6, 1 - 1e-6)
        dz = z * (1 - z)
        dpa = (1 - c) * dz * (thetas - b)
        dpb = -(1 - c) * dz * a
        r = (u - p) / (p * (1 - p))
        g = np.array([(r * dpa).sum(), (r * dpb).sum()])
        wgt = 1 / (p * (1 - p))
        h = -np.array([[(wgt * dpa * dpa).sum(), (wgt * dpa * dpb).sum()],
                       [(wgt * dpa * dpb).sum(), (wgt * dpb * dpb).sum()]]) - np.eye(2) * 1e-3
        step = np.linalg.solve(h, g)
        a = float(np.clip(a - 0.7 * step[0], 0.2, 3.5))
        b = float(np.clip(b - 0.7 * step[1], -4, 4))
    return a, b


# ------------------------------------------------------------------ калибровка (MML-EM, 2PL/3PL с фикс. c)
def calibrate(responses: np.ndarray, c: np.ndarray, n_iter: int = 60,
              a0: np.ndarray | None = None, b0: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Оценка параметров заданий (a, b) по матрице ответов методом маргинального правдоподобия (EM, Bock–Aitkin).

    responses: матрица N×J из {0, 1, nan} (nan — задание не показывалось: адаптивный тест даёт разреженную матрицу).
    c: фиксированные параметры угадывания (1/число вариантов).
    Используется для перевода заданий из «претеста» в рабочий банк и для валидации.
    """
    n, j = responses.shape
    nodes = np.linspace(-4, 4, 41)
    prior = np.exp(-0.5 * nodes ** 2)
    prior /= prior.sum()
    a = np.ones(j) if a0 is None else a0.copy()
    b = np.zeros(j) if b0 is None else b0.copy()
    mask = ~np.isnan(responses)
    u = np.nan_to_num(responses)

    for _ in range(n_iter):
        # E-шаг: апостериор по узлам для каждого кандидата
        p = c[None, :] + (1 - c[None, :]) / (1 + np.exp(-a[None, :] * (nodes[:, None] - b[None, :])))  # Q×J
        p = np.clip(p, 1e-6, 1 - 1e-6)
        loglik = (mask[:, None, :] * (u[:, None, :] * np.log(p)[None] + (1 - u[:, None, :]) * np.log(1 - p)[None])).sum(-1)
        loglik += np.log(prior)[None, :]
        loglik -= loglik.max(1, keepdims=True)
        post = np.exp(loglik)
        post /= post.sum(1, keepdims=True)  # N×Q
        # ожидаемые числа попыток и верных ответов в узлах
        n_q = post.T @ mask            # Q×J
        r_q = post.T @ (u * mask)      # Q×J
        # M-шаг: несколько шагов Ньютона по (a, b) для каждого задания
        for _ in range(3):
            z = 1 / (1 + np.exp(-a[None, :] * (nodes[:, None] - b[None, :])))
            pq = c[None, :] + (1 - c[None, :]) * z
            pq = np.clip(pq, 1e-6, 1 - 1e-6)
            dz = z * (1 - z)
            # dP/da = (1-c)·z(1-z)·(θ-b);  dP/db = −(1-c)·z(1-z)·a
            dpa = (1 - c[None, :]) * dz * (nodes[:, None] - b[None, :])
            dpb = -(1 - c[None, :]) * dz * a[None, :]
            resid = (r_q - n_q * pq) / (pq * (1 - pq))
            ga = (resid * dpa).sum(0)
            gb = (resid * dpb).sum(0)
            wgt = n_q / (pq * (1 - pq))
            haa = -(wgt * dpa ** 2).sum(0) - 1e-3
            hbb = -(wgt * dpb ** 2).sum(0) - 1e-3
            a = np.clip(a - ga / haa * 0.7, 0.2, 3.5)
            b = np.clip(b - gb / hbb * 0.7, -4, 4)
    return a, b
