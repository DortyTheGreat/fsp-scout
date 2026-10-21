"""Перевод достижений ФСП в сигналы для подбора.

Сила результата (одно достижение) = уровень соревнования × качество результата × размер поля × давность:
  • уровень: региональные 1 → межрегиональные 1,6 → всероссийские 3 → международные 4;
  • качество результата — место в процентилях поля с упором на верх таблицы (pct², победа ×2, призёр ×1,6,
    топ-10% ×1,25); в алгоритмических дисциплинах дополнительно доля решённых задач;
  • размер поля: 5-е место из 500 значит больше, чем 5-е из 15 (логарифм числа участников);
  • давность: результат двухлетней давности весит вдвое меньше свежего (затухание exp(−лет/3)).

Каждое достижение подтверждает конкретные навыки: дисциплина (алгоритмическое → алгоритмы, ИБ → безопасность и
сети), стек результата (командный — с меньшим весом: не всё делал участник) и роль в команде.

Под конкретный запрос работодателя (ranker.fsp_for_request) сила результата умножается на его релевантность
запросу: близость дисциплины специализации и долю обязательных и желательных навыков запроса, которые этот
результат подтверждает. Поэтому призёр всероссийского хакатона со стеком Python/PostgreSQL поднимается в выдаче
под запрос «бэкенд на Python», а тот же результат со стеком React — меньше.

Достижения ФСП не определяют категорию (это делает тест), а поднимают кандидата внутри категории и служат
независимым подтверждением навыков. Нет истории ФСП → 0, без штрафа.
"""
import math
from datetime import date

LEVEL_W = {"regional": 1.0, "interregional": 1.6, "national": 3.0, "international": 4.0}
RANK_W = {"3 юношеский разряд": 0.2, "3 разряд": 0.4, "2 разряд": 0.7, "1 разряд": 1.0, "КМС": 1.6, "МС": 2.2}

DISC_SKILLS = {
    "algorithmic": {"algorithms": 1.0},
    "product": {"system_design": 0.4, "http_api": 0.4, "git": 0.5},
    "security": {"security": 1.0, "networking": 0.6, "linux": 0.6},
    "robotics": {"cpp": 0.5, "algorithms": 0.5},
    "drones": {"cpp": 0.5, "algorithms": 0.6},
}
STACK_SKILL = {
    "python": "python", "fastapi": "web_frameworks", "django": "web_frameworks", "spring": "web_frameworks",
    "postgresql": "postgresql", "sql": "sql", "react": "react", "docker": "docker", "kubernetes": "kubernetes",
    "java": "java", "go": "go", "kafka": "caching_queues", "redis": "caching_queues", "pytorch": "deep_learning",
    "pandas": "pandas", "catboost": "ml", "typescript": "typescript", "nodejs": "javascript", "cpp": "cpp",
    "linux": "linux", "networking": "networking", "web": "security", "opencv": "deep_learning", "ros": "cpp",
}
# роль в командном результате → навыки, которые она подтверждает
ROLE_SKILLS = {
    "бэкенд": {"http_api": 0.6, "system_design": 0.4, "sql": 0.4},
    "фронтенд": {"react": 0.5, "javascript": 0.5, "html_css": 0.5},
    "фулстек": {"http_api": 0.5, "javascript": 0.4, "react": 0.3},
    "ml": {"ml": 0.6, "pandas": 0.4},
    "devops": {"docker": 0.6, "ci_cd": 0.6, "linux": 0.5},
    "аналитик": {"sql": 0.5, "statistics": 0.5},
    "капитан": {"system_design": 0.3},
}
ROLE_SPEC = {"бэкенд": "backend", "фронтенд": "frontend", "фулстек": "backend", "ml": "data_science",
             "devops": "devops", "аналитик": "data_science"}
SPEC_DISC = {
    "backend": {"product": 1.0, "algorithmic": 0.7, "security": 0.5, "robotics": 0.3, "drones": 0.3},
    "frontend": {"product": 1.0, "algorithmic": 0.5, "security": 0.3, "robotics": 0.2, "drones": 0.2},
    "data_science": {"product": 0.8, "algorithmic": 0.8, "robotics": 0.5, "drones": 0.5, "security": 0.3},
    "devops": {"product": 0.8, "security": 0.9, "algorithmic": 0.4, "robotics": 0.3, "drones": 0.3},
    "qa": {"product": 0.8, "security": 0.7, "algorithmic": 0.4, "robotics": 0.3, "drones": 0.3},
}


def result_quality(a: dict) -> tuple[float, str]:
    """Качество результата без учёта уровня и давности + понятная подпись («Призёр, 2 место из 120»)."""
    total = max(1, int(a.get("participants_total") or 1))
    place = min(total, max(1, int(a.get("place") or total)))
    pct = 1.0 - (place - 1) / total
    q = pct ** 2
    if place == 1:
        q, label = q * 2.0, "Победитель"
    elif place <= 3:
        q, label = q * 1.6, "Призёр"
    elif pct >= 0.9:
        q, label = q * 1.25, "Топ-10%"
    elif pct >= 0.75:
        label = "Топ-25%"
    else:
        label = "Участник"
    if a.get("tasks_total"):
        q *= 0.75 + 0.5 * min(1.0, (a.get("tasks_solved") or 0) / a["tasks_total"])
    return q, f"{label}, {place} место из {total}"


def strength(a: dict, today: date | None = None) -> float:
    today = today or date.today()
    total = max(1, int(a.get("participants_total") or 1))
    q, _ = result_quality(a)
    field = min(1.25, 0.6 + 0.12 * math.log(total))
    years = max(0.0, (today - date.fromisoformat(a["date"])).days / 365.0)
    return LEVEL_W.get(a.get("level"), 1.0) * q * field * math.exp(-years / 3.0)


def _role_keys(role: str | None) -> list[str]:
    r = (role or "").lower()
    return [k for k in ROLE_SKILLS if k in r]


def achievement_skills(a: dict) -> dict[str, float]:
    """Какие навыки и насколько уверенно подтверждает результат (0–1)."""
    contrib = dict(DISC_SKILLS.get(a.get("discipline"), {}))
    # стек командного результата атрибутируем участнику с меньшим весом: не всё делал он сам
    stack_w = 0.5 if a.get("format") == "team" else 0.8
    for st in a.get("stack") or []:
        sk = STACK_SKILL.get(st)
        if sk:
            contrib[sk] = max(contrib.get(sk, 0), stack_w)
    for key in _role_keys(a.get("role")):
        for sk, w in ROLE_SKILLS[key].items():
            contrib[sk] = max(contrib.get(sk, 0), w)
    return contrib


def spec_relevance(a: dict, spec: str) -> float:
    rel = SPEC_DISC.get(spec, {}).get(a.get("discipline"), 0.2)
    if any(ROLE_SPEC.get(k) == spec for k in _role_keys(a.get("role"))):
        rel = 1.0  # роль в команде совпадает со специализацией запроса
    return rel


def _norm(raw: float, scale: float = 3.0) -> float:
    return round(1.0 - math.exp(-raw / scale), 4)


def item_view(a: dict, today: date | None = None) -> dict:
    q, label = result_quality(a)
    return {"id": a["id"], "event": a.get("event_name"), "discipline": a.get("discipline"),
            "discipline_name": a.get("discipline_name"), "level": a.get("level"), "level_name": a.get("level_name"),
            "date": a["date"], "place": a.get("place"), "participants_total": a.get("participants_total"),
            "format": a.get("format"), "role": a.get("role"), "team_name": a.get("team_name"),
            "is_prize": (a.get("place") or 99) <= 3, "result": label, "strength": round(strength(a, today), 4),
            "skills": {k: round(v, 2) for k, v in achievement_skills(a).items()}}


def summarize(items: list[dict], sport_rank: str | None, today: date | None = None) -> dict:
    """Сводка для профиля и ранжирования. Работает и для пустого списка (нет истории ФСП)."""
    by_disc: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    views = []
    raw_total = 0.0
    for a in items:
        if not a.get("verified", True):
            continue  # неподтверждённые подписью записи не учитываем
        v = item_view(a, today)
        views.append(v)
        s = v["strength"]
        raw_total += s
        d = by_disc.setdefault(a["discipline"], {"count": 0, "prizes": 0, "best_place": None, "best_pct": 0.0,
                                                  "strength": 0.0, "name": a.get("discipline_name")})
        d["count"] += 1
        d["prizes"] += 1 if a.get("place", 99) <= 3 else 0
        d["strength"] = round(d["strength"] + s, 4)
        pct = 1 - (a["place"] - 1) / max(1, a["participants_total"])
        if pct > d["best_pct"]:
            d["best_pct"], d["best_place"] = round(pct, 3), f"{a['place']} из {a['participants_total']}"
        for sk, w in v["skills"].items():
            e = skills.setdefault(sk, {"strength": 0.0, "evidence": []})
            e["strength"] = round(e["strength"] + s * w, 4)
            e["evidence"].append({"achievement_id": a["id"], "event": a["event_name"], "date": a["date"],
                                  "place": a["place"], "participants_total": a["participants_total"],
                                  "level": a.get("level_name"), "role": a.get("role"), "result": v["result"],
                                  "strength": s})
    for e in skills.values():
        e["evidence"].sort(key=lambda x: -x["strength"])  # сначала самые сильные результаты
    rank_bonus = RANK_W.get(sport_rank or "", 0.0)
    score_by_spec = {}
    for spec, rel in SPEC_DISC.items():
        raw = sum(v["strength"] * rel.get(k, 0.2) for k, v in by_disc.items()) + rank_bonus
        score_by_spec[spec] = _norm(raw)
    for v in skills.values():
        v["level"] = _norm(v["strength"], 2.0)
    views.sort(key=lambda x: -x["strength"])
    return {
        "has_history": bool(items),
        "total": len(items),
        "prizes": sum(1 for a in items if a.get("place", 99) <= 3),
        "sport_rank": sport_rank,
        "by_discipline": by_disc,
        "skills": skills,
        "items": views,
        "score": _norm(raw_total + rank_bonus),
        "score_by_spec": score_by_spec,
        "version": 2,
    }


def ensure_summary(fsp_data: dict | None) -> dict:
    """Сводка текущей версии: старые профили (без разбивки по достижениям) пересчитываются из сырых записей."""
    data = fsp_data or {}
    summ = data.get("summary") or {}
    if summ.get("version") == 2 or not data.get("items"):
        return summ
    return summarize(data["items"], (data.get("participant") or {}).get("sport_rank") or summ.get("sport_rank"))
