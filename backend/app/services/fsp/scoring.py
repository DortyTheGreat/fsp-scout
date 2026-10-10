"""Перевод достижений ФСП в сигналы для подбора.

Сила достижения = вес уровня × перцентиль места × бонус за призовое место × затухание по давности.
Отдельно считается релевантность дисциплин специализации (продуктовое программирование ближе бэкенду,
ИБ — DevOps и QA и т.д.) и вклад в конкретные навыки (стек, заявленный в результатах).

Важно: достижения ФСП не определяют категорию кандидата (это делает тест), а повышают его
позицию внутри категории и служат независимым подтверждением навыков. Нет истории ФСП → 0, без штрафа.
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
SPEC_DISC = {
    "backend": {"product": 1.0, "algorithmic": 0.7, "security": 0.5, "robotics": 0.3, "drones": 0.3},
    "frontend": {"product": 1.0, "algorithmic": 0.5, "security": 0.3, "robotics": 0.2, "drones": 0.2},
    "data_science": {"product": 0.8, "algorithmic": 0.8, "robotics": 0.5, "drones": 0.5, "security": 0.3},
    "devops": {"product": 0.8, "security": 0.9, "algorithmic": 0.4, "robotics": 0.3, "drones": 0.3},
    "qa": {"product": 0.8, "security": 0.7, "algorithmic": 0.4, "robotics": 0.3, "drones": 0.3},
}


def strength(a: dict, today: date | None = None) -> float:
    today = today or date.today()
    total = max(1, int(a.get("participants_total") or 1))
    place = max(1, int(a.get("place") or total))
    pct = 1.0 - (place - 1) / total
    prize = 1.5 if place <= 3 else (1.2 if pct >= 0.9 else 1.0)
    years = max(0.0, (today - date.fromisoformat(a["date"])).days / 365.0)
    return LEVEL_W.get(a.get("level"), 1.0) * pct * prize * math.exp(-years / 3.0)


def _norm(raw: float, scale: float = 3.0) -> float:
    return round(1.0 - math.exp(-raw / scale), 4)


def summarize(items: list[dict], sport_rank: str | None, today: date | None = None) -> dict:
    """Сводка для профиля и ранжирования. Работает и для пустого списка (нет истории ФСП)."""
    by_disc: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    raw_total = 0.0
    for a in items:
        if not a.get("verified", True):
            continue  # неподтверждённые подписью записи не учитываем
        s = strength(a, today)
        raw_total += s
        d = by_disc.setdefault(a["discipline"], {"count": 0, "prizes": 0, "best_place": None, "best_pct": 0.0,
                                                  "strength": 0.0, "name": a.get("discipline_name")})
        d["count"] += 1
        d["prizes"] += 1 if a.get("place", 99) <= 3 else 0
        d["strength"] = round(d["strength"] + s, 4)
        pct = 1 - (a["place"] - 1) / max(1, a["participants_total"])
        if pct > d["best_pct"]:
            d["best_pct"], d["best_place"] = round(pct, 3), f"{a['place']} из {a['participants_total']}"
        contrib = dict(DISC_SKILLS.get(a["discipline"], {}))
        # стек командного результата атрибутируем участнику с меньшим весом: не всё делал он сам
        stack_w = 0.4 if a.get("format") == "team" else 0.8
        for st in a.get("stack") or []:
            sk = STACK_SKILL.get(st)
            if sk:
                contrib[sk] = max(contrib.get(sk, 0), stack_w)
        for sk, w in contrib.items():
            e = skills.setdefault(sk, {"strength": 0.0, "evidence": []})
            e["strength"] = round(e["strength"] + s * w, 4)
            e["evidence"].append({"achievement_id": a["id"], "event": a["event_name"], "date": a["date"],
                                  "place": a["place"], "participants_total": a["participants_total"],
                                  "level": a.get("level_name"), "role": a.get("role")})
    rank_bonus = RANK_W.get(sport_rank or "", 0.0)
    score_by_spec = {}
    for spec, rel in SPEC_DISC.items():
        raw = sum(v["strength"] * rel.get(k, 0.2) for k, v in by_disc.items()) + rank_bonus
        score_by_spec[spec] = _norm(raw)
    for v in skills.values():
        v["level"] = _norm(v["strength"], 2.0)
    return {
        "has_history": bool(items),
        "total": len(items),
        "prizes": sum(1 for a in items if a.get("place", 99) <= 3),
        "sport_rank": sport_rank,
        "by_discipline": by_disc,
        "skills": skills,
        "score": _norm(raw_total + rank_bonus),
        "score_by_spec": score_by_spec,
    }
