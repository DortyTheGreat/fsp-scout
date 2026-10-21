"""Разбор текста на правилах: навыки, грейд, специализация, зарплата, формат, стаж, контакты.
Используется и для резюме, и для описания потребности работодателя; это же — запасной путь, когда LLM нет."""
from __future__ import annotations

import re
from datetime import date

from app.taxonomy import SKILL_BY_SLUG, SKILLS, SPECIALIZATIONS, SOFT_SKILLS

CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород", "Самара",
          "Томск", "Пермь", "Краснодар", "Иннополис", "Ростов-на-Дону", "Владивосток", "Уфа", "Воронеж"]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
TG_RE = re.compile(r"(?:t\.me/|telegram[:\s]+@?|tg[:\s]+@?|(?<![\w.])@)([A-Za-z][\w]{4,31})", re.I)


def _pad(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


def extract_skills(text: str) -> list[str]:
    t = _pad(text)
    found = []
    for s in SKILLS:
        for syn in s.synonyms:
            w = syn.lower().strip()
            if not w.replace("-", "").isalnum():          # «c++», «ci/cd», «next.js» — подстрокой
                hit = re.search(rf"(?<![\w]){re.escape(w)}", t) is not None
            elif len(w) <= 4:                                 # короткие: целым словом (java ≠ javascript)
                hit = re.search(rf"(?<![\w+#.]){re.escape(w)}(?![\w+#])", t) is not None
            else:                                             # длинные/основы: с начала слова
                hit = re.search(rf"(?<![\w+#.]){re.escape(w)}", t) is not None
            if hit:
                found.append(s.slug)
                break
    return found


def extract_grade(text: str) -> str | None:
    t = _pad(text)
    rules = [("senior", r"senior|сеньор|синьор|ведущ|lead |тимлид|старш"), ("middle", r"middle|мидл"),
             ("junior", r"junior|джун|младш|начинающ"), ("intern", r"стаж[её]р|intern|без опыта|студент")]
    for g, rx in rules:
        if re.search(rx, t):
            return g
    m = re.search(r"(?:опыт\w*|от)\s*(\d+)\+?\s*(?:год|лет)", t)
    if m:
        y = int(m.group(1))
        return "senior" if y >= 4 else ("middle" if y >= 2 else "junior")
    return None


def extract_specialization(text: str) -> str | None:
    t = _pad(text)
    best, best_score = None, 0
    for sp in SPECIALIZATIONS:
        score = sum(2 for a in sp.aliases if a in t)
        if score > best_score:
            best, best_score = sp.slug, score
    if best:
        return best
    skills = extract_skills(text)
    votes = {sp.slug: sum(1 for s in skills if s in sp.core_skills) for sp in SPECIALIZATIONS}
    top = max(votes.items(), key=lambda kv: kv[1])
    return top[0] if top[1] else None


def _num(s: str) -> int:
    s = s.replace(" ", "").replace(" ", "")
    s = s.rstrip(".")
    mult = 1000 if s.lower().endswith(("к", "k", "тыс")) else 1
    s = re.sub(r"[^\d]", "", s)
    return int(s) * mult if s else 0


def extract_salary(text: str) -> tuple[int | None, int | None]:
    t = text.lower().replace(" ", " ")
    num = r"(\d[\d ]{1,8}(?:\s?(?:к|k|тыс\.?))?)"
    m = re.search(rf"{num}\s*(?:-|–|—|до)\s*{num}\s*(?:₽|руб|р\b|тыс|k|к)?", t)
    if m:
        a, b = _num(m.group(1)), _num(m.group(2))
        if b and a < 1000 and b >= 1000:
            a *= 1000
        if 10_000 <= a <= b <= 10_000_000:
            return a, b
    m = re.search(rf"от\s*{num}", t)
    if m and 10_000 <= _num(m.group(1)) <= 10_000_000:
        return _num(m.group(1)), None
    m = re.search(rf"до\s*{num}", t)
    if m and 10_000 <= _num(m.group(1)) <= 10_000_000:
        return None, _num(m.group(1))
    m = re.search(rf"{num}\s*(?:₽|руб)", t)  # фиксированная сумма
    if m and 10_000 <= _num(m.group(1)) <= 10_000_000:
        return _num(m.group(1)), _num(m.group(1))
    return None, None


def extract_formats(text: str) -> list[str]:
    t = _pad(text)
    out = []
    if re.search(r"удал[её]н|remote|из любой точки", t):
        out.append("remote")
    if re.search(r"гибрид|hybrid", t):
        out.append("hybrid")
    if re.search(r"офис|office|на месте", t):
        out.append("office")
    return out


def extract_city(text: str) -> str | None:
    for c in CITIES:
        if c.lower() in text.lower():
            return c
    if re.search(r"\bмск\b", text.lower()):
        return "Москва"
    if re.search(r"\bспб\b|питер", text.lower()):
        return "Санкт-Петербург"
    return None


_MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8, "сен": 9,
           "окт": 10, "ноя": 11, "дек": 12}


_TOTAL_RE = re.compile(r"опыт\w*(?:\s+\w+){0,3}?[:\s—-]+(\d+)\s*(?:год|лет)(?:\D{0,4}(\d+)\s*мес)?")


def extract_years_total(text: str) -> float | None:
    """Явно написанный итог стажа: «Опыт работы — 6 лет 2 месяца»."""
    m = _TOTAL_RE.search(text.lower())
    if m:
        return round(int(m.group(1)) + (int(m.group(2)) / 12 if m.group(2) else 0), 1)
    return None


def extract_years_experience(text: str, today: date | None = None) -> float | None:
    today = today or date.today()
    t = text.lower()
    total = extract_years_total(text)
    if total is not None:
        return total
    # диапазоны «03.2021 — 06.2023», «март 2020 — настоящее время», «2019–2022»
    total = 0.0
    rng_re = re.compile(r"(?:(\d{1,2})[./]|([а-я]{3})[а-я]*\s+)?((?:19|20)\d{2})\s*[-–—]\s*(?:(?:(\d{1,2})[./]|([а-я]{3})[а-я]*\s+)?((?:19|20)\d{2})|(настоящ|н\.в|по сей|сейчас|now|present))")
    for g in rng_re.finditer(t):
        m1 = int(g.group(1)) if g.group(1) else _MONTHS.get(g.group(2) or "", 1)
        y1 = int(g.group(3))
        if g.group(7):
            y2, m2 = today.year, today.month
        else:
            m2 = int(g.group(4)) if g.group(4) else _MONTHS.get(g.group(5) or "", 12)
            y2 = int(g.group(6))
        months = (y2 - y1) * 12 + (m2 - m1)
        if 0 < months < 600:
            total += months / 12
    return round(total, 1) if total else None


def extract_contacts(text: str) -> dict:
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    tg = None
    for m in TG_RE.finditer(text):
        if email and m.group(1).lower() in email.group(0).lower():
            continue
        tg = "@" + m.group(1)
        break
    return {"email": email.group(0) if email else None, "phone": re.sub(r"[^\d+]", "", phone.group(0)) if phone else None,
            "telegram": tg}


def extract_name(text: str) -> str | None:
    for line in text.splitlines()[:8]:
        line = line.strip()
        if re.fullmatch(r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?", line):
            return line
    return None


def extract_soft_skills(text: str) -> list[str]:
    t = text.lower()
    keys = {"Коммуникация": ["коммуникаб", "коммуникац"], "Работа в команде": ["команд"],
            "Лидерство": ["лидер", "руковод", "тимлид"], "Самоорганизация": ["самоорганиз", "ответствен"],
            "Наставничество": ["наставни", "ментор"], "Публичные выступления": ["выступ", "доклад", "спикер"],
            "Решение конфликтов": ["конфликт"], "Тайм-менеджмент": ["тайм-менедж", "дедлайн"]}
    return [k for k, vs in keys.items() if any(v in t for v in vs) and k in SOFT_SKILLS]


def extract_roles(text: str) -> list[str]:
    t = text.lower()
    out = []
    if re.search(r"тимлид|team ?lead|руководил", t):
        out.append("team_lead")
    if re.search(r"ментор|наставни", t):
        out.append("mentor")
    if re.search(r"архитект", t):
        out.append("architect")
    if re.search(r"капитан", t):
        out.append("captain")
    return out or ["individual"]


def split_must_nice(text: str, skills: list[str]) -> tuple[list[str], list[str]]:
    """Навыки из блока «будет плюсом / желательно» — nice-to-have, остальные — must-have."""
    t = text.lower()
    m = re.search(r"(будет плюсом|желательно|приветствуется|nice to have|плюсом будет)(.*)", t, flags=re.S)
    nice = set(extract_skills(m.group(2))) if m else set()
    head = t[: m.start()] if m else t
    must = [s for s in skills if s in set(extract_skills(head))]
    nice_l = [s for s in skills if s in nice and s not in must]
    return must, nice_l


def skill_names(slugs: list[str]) -> list[str]:
    return [SKILL_BY_SLUG[s].name for s in slugs if s in SKILL_BY_SLUG]
