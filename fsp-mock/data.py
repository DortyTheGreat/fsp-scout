"""Синтетический реестр ФСП: участники, мероприятия, результаты.

Структура данных — предложение команды для боевой интеграции (API ФСП в рамках хакатона не выдаётся).
Генерация детерминирована (seed), поэтому идентификаторы стабильны между перезапусками.
"""
import random
from datetime import date, timedelta

DISCIPLINES = {
    "algorithmic": "Алгоритмическое программирование",
    "product": "Продуктовое программирование",
    "security": "Программирование систем информационной безопасности",
    "robotics": "Программирование робототехники",
    "drones": "Программирование беспилотных авиационных систем",
}
LEVELS = {
    "regional": "Региональные соревнования",
    "interregional": "Межрегиональные соревнования",
    "national": "Всероссийские соревнования",
    "international": "Международные соревнования",
}
SPORT_RANKS = [None, None, None, "3 юношеский разряд", "3 разряд", "2 разряд", "1 разряд", "КМС", "МС"]
REGIONS = ["Москва", "Санкт-Петербург", "Республика Татарстан", "Новосибирская область", "Свердловская область",
           "Нижегородская область", "Краснодарский край", "Томская область", "Самарская область", "Пермский край"]
STACKS = {
    "product": [["python", "fastapi", "postgresql", "react", "docker"], ["java", "spring", "postgresql", "react"],
                ["go", "postgresql", "kafka", "docker"], ["python", "pytorch", "pandas"], ["typescript", "react", "nodejs"],
                ["python", "django", "redis", "docker", "kubernetes"], ["python", "catboost", "pandas", "sql"]],
    "algorithmic": [["cpp"], ["python"], ["cpp", "python"], ["java"]],
    "security": [["python", "linux", "networking"], ["cpp", "linux", "reverse"], ["python", "web", "sql"]],
    "robotics": [["cpp", "ros"], ["python", "opencv"]],
    "drones": [["cpp", "px4"], ["python", "opencv", "ros"]],
}
ROLES_PRODUCT = ["Капитан, бэкенд", "Бэкенд-разработчик", "Фронтенд-разработчик", "ML-инженер", "DevOps", "Аналитик",
                 "Капитан, фулстек", "Дизайнер-разработчик"]
FIRST = ["Александр", "Дмитрий", "Максим", "Иван", "Артём", "Никита", "Михаил", "Егор", "Андрей", "Илья",
         "Анна", "Мария", "Елена", "Дарья", "Алина", "Ксения", "Полина", "София", "Виктория", "Екатерина"]
LAST = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
        "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев"]


def _fio(rng: random.Random) -> tuple[str, str]:
    i = rng.randrange(len(FIRST))
    last = rng.choice(LAST)
    female = i >= 10
    if female:
        last = last + "а" if last.endswith(("ов", "ев", "ин", "ёв")) else last
    return f"{last} {FIRST[i]}", ("f" if female else "m")


def build_events(rng: random.Random) -> list[dict]:
    events = []
    eid = 1
    start = date(2022, 3, 1)
    for year in range(2022, 2027):
        for disc in DISCIPLINES:
            for level in LEVELS:
                if level == "international" and disc not in ("algorithmic", "product"):
                    continue
                if rng.random() < 0.35 and level != "national":
                    continue
                d = date(year, rng.randint(1, 12), rng.randint(1, 28))
                if d > date(2026, 9, 30):
                    continue
                name = {
                    "regional": f"Региональные соревнования по спортивному программированию ({rng.choice(REGIONS)})",
                    "interregional": "Межрегиональные соревнования по спортивному программированию",
                    "national": rng.choice(["Чемпионат России по спортивному программированию",
                                            "Кубок России по спортивному программированию",
                                            "Всероссийские соревнования по спортивному программированию"]),
                    "international": "Международные соревнования по спортивному программированию",
                }[level]
                fmt = "team" if disc != "algorithmic" or rng.random() < 0.5 else "individual"
                events.append({"id": eid, "name": f"{name} — {DISCIPLINES[disc].lower()}", "discipline": disc,
                               "discipline_name": DISCIPLINES[disc], "level": level, "level_name": LEVELS[level],
                               "date": d.isoformat(), "format": fmt,
                               "participants_total": rng.choice([40, 60, 80, 120, 200, 350, 500]) if level != "regional"
                               else rng.choice([15, 25, 40, 60])})
                eid += 1
    _ = start
    return events


def build_participants(rng: random.Random, events: list[dict], n: int = 400) -> list[dict]:
    people = []
    for k in range(1, n + 1):
        fio, sex = _fio(rng)
        fsp_id = f"FSP-{k:06d}"
        activity = rng.random()
        n_results = 0 if activity < 0.22 else (rng.randint(1, 3) if activity < 0.7 else rng.randint(3, 9))
        main_disc = rng.choices(list(DISCIPLINES), weights=[35, 40, 12, 7, 6])[0]
        skill = rng.random()  # скрытая «сила» участника — влияет на места
        results = []
        pool = [e for e in events if e["discipline"] == main_disc or rng.random() < 0.15]
        for ev in rng.sample(pool, min(n_results, len(pool))):
            total = ev["participants_total"]
            pct = min(0.999, max(0.0, rng.betavariate(1 + 4 * (1 - skill), 1 + 4 * skill)))
            place = max(1, int(pct * total))
            r = {"event_id": ev["id"], "place": place, "participants_total": total,
                 "score": round((1 - pct) * 100, 1), "date": ev["date"]}
            if ev["format"] == "team":
                r["team_name"] = rng.choice(["veni vidi vivii", "Байтовые гвозди", "NullPointer", "Сибирские бобры",
                                             "Out of Bounds", "Код да Винчи", "Ctrl+Alt+Win", "MISIS Hackers",
                                             "Синие Котики", "Tensor Flowers"]) + f" #{rng.randint(1, 99)}"
                r["role"] = rng.choice(ROLES_PRODUCT) if ev["discipline"] == "product" else rng.choice(["Капитан", "Участник"])
            if ev["discipline"] in STACKS:
                r["stack"] = rng.choice(STACKS[ev["discipline"]])
            if ev["discipline"] == "algorithmic":
                tt = rng.choice([8, 10, 12])
                r["tasks_total"] = tt
                r["tasks_solved"] = max(0, min(tt, int(round((1 - pct) * tt + rng.uniform(-1, 1)))))
            results.append(r)
        rank = None
        if results:
            best = min(r["place"] / r["participants_total"] for r in results)
            rank = rng.choice(SPORT_RANKS[4:7]) if best < 0.1 else rng.choice(SPORT_RANKS)
        people.append({"fsp_id": fsp_id, "full_name": fio, "sex": sex, "birth_year": rng.randint(1994, 2008),
                       "region": rng.choice(REGIONS), "sport_rank": rank,
                       "email": f"participant{k}@fsp.example", "results": sorted(results, key=lambda r: r["date"])})
    # Демо-участники с понятными данными
    people.append({"fsp_id": "FSP-000777", "full_name": "Демидова Анна", "sex": "f", "birth_year": 2002,
                   "region": "Москва", "sport_rank": "1 разряд", "email": "anna.demo@fsp.example",
                   "results": _demo_results(events)})
    people.append({"fsp_id": "FSP-000778", "full_name": "Новичков Пётр", "sex": "m", "birth_year": 2004,
                   "region": "Томская область", "sport_rank": None, "email": "petr.demo@fsp.example", "results": []})
    return people


def _demo_results(events: list[dict]) -> list[dict]:
    out = []
    prod = [e for e in events if e["discipline"] == "product" and e["level"] == "national"][-2:]
    alg = [e for e in events if e["discipline"] == "algorithmic" and e["level"] in ("national", "interregional")][-2:]
    for ev, place, role, stack in zip(prod, [2, 5], ["Капитан, бэкенд", "Бэкенд-разработчик"],
                                      [["python", "fastapi", "postgresql", "docker"], ["python", "django", "redis"]]):
        out.append({"event_id": ev["id"], "place": place, "participants_total": ev["participants_total"],
                    "score": 91.0 - place, "date": ev["date"], "team_name": "veni vidi vivii", "role": role,
                    "stack": stack})
    for ev, place in zip(alg, [14, 31]):
        out.append({"event_id": ev["id"], "place": place, "participants_total": ev["participants_total"],
                    "score": 70.0, "date": ev["date"], "tasks_total": 10, "tasks_solved": 7, "stack": ["python", "cpp"]})
    return sorted(out, key=lambda r: r["date"])


_rng = random.Random(2026)
EVENTS = build_events(_rng)
EVENT_BY_ID = {e["id"]: e for e in EVENTS}
PARTICIPANTS = build_participants(_rng, EVENTS)
PARTICIPANT_BY_ID = {p["fsp_id"]: p for p in PARTICIPANTS}
_ = timedelta
