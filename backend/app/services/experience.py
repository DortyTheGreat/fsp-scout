"""Опыт работы из текста резюме правилами: место работы, должность, период, описание.

Как устроено:
  1. Ищем раздел опыта по заголовку («Опыт работы», «Трудовая деятельность», «Experience»…) и обрезаем его
     на следующем заголовке («Образование», «Навыки», «Курсы»…). Нет заголовка — смотрим весь текст, но
     строки про учёбу и курсы пропускаем: период учёбы не стаж.
  2. Каждая строка с периодом («Март 2021 — настоящее время», «03.2021 – 05.2024», «2019–2022»,
     «Jan 2021 - Present», «с 05.2019 по 08.2021») начинает запись.
  3. Место работы и должность берём из той же строки («ООО «Ромашка», разработчик, 03.2021 — …»,
     «Сбер | Data Scientist | 09.2021 – 05.2024», «Python Developer, Tinkoff (2020 — 2023)») либо из коротких
     строк рядом. Вёрстка определяется по первой записи: шапка до дат (LinkedIn) или после (выгрузка hh.ru).
     Должность — строка со словом-ролью (разработчик, инженер, analyst…), компания — строка с признаком
     организации (ООО, «…», LLC, Bank…) или первая короткая строка без роли; города и сайты пропускаем.
  4. Стаж по записям — объединение периодов: параллельная работа не считается дважды, учёба не считается.
"""
from __future__ import annotations

import re
from datetime import date

from app.services.nlp import CITIES

_MONTH_WORDS = [
    (r"январ\w*|jan\w*", 1), (r"феврал\w*|feb\w*", 2), (r"март\w*|mar\w*", 3), (r"апрел\w*|apr\w*", 4),
    (r"ма[йя]\w*|may", 5), (r"июн\w*|jun\w*", 6), (r"июл\w*|jul\w*", 7), (r"август\w*|aug\w*", 8),
    (r"сентябр\w*|sep\w*", 9), (r"октябр\w*|oct\w*", 10), (r"ноябр\w*|nov\w*", 11), (r"декабр\w*|dec\w*", 12),
]
_MONTH_RE = "|".join(rx for rx, _ in _MONTH_WORDS)
_DATE = rf"(?:(?:{_MONTH_RE})\.?\s+|\d{{1,2}}[./])?(?:19|20)\d{{2}}(?:\s*г(?:ода?|\.)?)?"
_PRESENT = (r"(?:по\s+)?(?:настоящее\s+время|настоящий\s+момент|наст\.?\s*вр\w*|н\.\s*в\.?|н\.в\.?|сейчас|"
            r"текущее\s+время|сей\s+день|present|now|current|today)")
PERIOD_RE = re.compile(rf"(?:\bс\s+|\bfrom\s+)?(?P<a>{_DATE})\s*(?:[-–—]+|\bпо\b|\bto\b|\buntil\b|\btill\b)\s*(?P<b>{_DATE}|{_PRESENT})",
                       re.I)
_DATE_PARTS = re.compile(rf"(?:(?P<mw>{_MONTH_RE})\.?\s+|(?P<mn>\d{{1,2}})[./])?(?P<y>(?:19|20)\d{{2}})", re.I)

_EXP_HEAD = re.compile(r"^(?:опыт(?:\s+работы)?|места\s+работы|где\s+работал\w*|трудовая\s+деятельность|трудовой\s+стаж|"
                       r"профессиональный\s+опыт|коммерческий\s+опыт|work\s+experience|professional\s+experience|"
                       r"experience|work\s+history|employment(?:\s+history)?)\b", re.I)
_STOP_HEAD = re.compile(r"^(?:образование|education|ключевые\s+навыки|навыки|skills|технологии|стек|о\s+себе|about|"
                        r"проекты|pet-?проекты|projects|курсы|courses|сертификат\w*|certific\w*|языки|знание\s+языков|"
                        r"languages|дополнительн\w*|достижения|achievements|контакты|contacts|личные\s+качества|"
                        r"хобби|интересы|рекомендации|публикации|награды|повышение\s+квалификации|summary|"
                        r"желаемая\s+должность)\b", re.I)
_EDU_WORDS = re.compile(r"университет|институт|академи|колледж|техникум|школ[аы]|бакалавр|магистр|аспирант|студент|"
                        r"образовани|факультет|кафедр|university|college|institute|bachelor|master|school|курс|course|"
                        r"практикум|bootcamp", re.I)
ROLE_RE = re.compile(r"разработчик|программист|инженер|engineer|developer|аналитик|analyst|тестировщик|\bqa\b|devops|"
                     r"\bsre\b|тимлид|team\s?lead|tech\s?lead|\blead\b|архитектор|architect|стаж[её]р|\bintern\b|"
                     r"специалист|руководител|\bhead\b|manager|менеджер|scientist|администратор|administrator|"
                     r"консультант|consultant|\bcto\b|\bceo\b|founder|основател|дизайнер|designer|верстальщик|"
                     r"backend|frontend|fullstack|full-stack|\bml\b|mlops|\bdba\b|researcher|исследовател|"
                     r"преподавател|ментор|mentor|помощник|ассистент|assistant|оператор|техник\b|programmer", re.I)
_ORG_RE = re.compile(r"\b(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|ФГУП|ГУП|МУП|ГК|LLC|Inc|Ltd|GmbH|Corp|Co\.|Company|Group|Bank|Labs?|"
                     r"Studio|Systems|Solutions|Software|Digital|Technologies|Tech)\b|«|\"|Банк|банк|Лаборатори|"
                     r"Студия|Технолог|Групп|Холдинг|Фриланс|Freelance|Самозанят", re.I)
_DURATION_RE = re.compile(r"^\(?\s*(?:\d+\s*(?:год[а]?|лет|г\.|мес\w*|yrs?|years?|mos?|months?)\.?\s*){1,2}\)?$", re.I)
_DURATION_INLINE = re.compile(r"\(?\s*(?:\d+\s*(?:год[а]?|лет|мес\w*|yrs?|years?|mos?|months?)\.?\s*){1,2}\)?", re.I)
_EMPLOYMENT_TAIL = re.compile(r"\s*[·•]\s*(?:full[- ]time|part[- ]time|contract|internship|freelance|полная\s+занятость|"
                              r"частичная\s+занятость|удал[её]нн\w*|remote|hybrid|on-site|гибрид\w*)\b.*$", re.I)
_BULLET = re.compile(r"^\s*(?:[—–\-•*·▪●○]|\d+[.)])\s+")
_URL = re.compile(r"(?:https?://|www\.|\b[\w-]+\.(?:ru|com|io|org|net|рф|tech|dev)\b)", re.I)
_LABEL_COMPANY = re.compile(r"^(?:компания|организация|место\s+работы|работодатель|company|employer|organi[sz]ation)\s*[:—–-]\s*(.+)$", re.I)
_LABEL_POSITION = re.compile(r"^(?:должность|позиция|роль|position|title|role)\s*[:—–-]\s*(.+)$", re.I)
_LABEL_PERIOD = re.compile(r"^(?:период(?:\s+работы)?|даты|сроки?|время\s+работы|period|dates)\s*[:—–-]?\s*", re.I)
_DESC_LABEL = re.compile(r"^(?:обязанности|задачи|достижения|стек|технологии|проекты|результаты|описание|функционал|"
                         r"responsibilities|achievements|stack|technologies|tech|duties|description)\s*:", re.I)
_SEP = re.compile(r"\s+\|\s+|\s+[—–]\s+|\s+-\s+|,\s+|\s+·\s+|\s+at\s+|\s+@\s+")


def _month_of(word: str) -> int:
    for rx, m in _MONTH_WORDS:
        if re.fullmatch(rx, word.lower()):
            return m
    return 0


def _parse_date(s: str, end: bool, today: date) -> tuple[int, int] | None:
    """(год, месяц). Только год: середина года — тогда «2019–2022» даёт ровно 3 года."""
    if re.fullmatch(_PRESENT, s.strip(), re.I):
        return today.year, today.month
    m = _DATE_PARTS.search(s)
    if not m:
        return None
    y = int(m.group("y"))
    if m.group("mw"):
        mon = _month_of(m.group("mw"))
    elif m.group("mn"):
        mon = int(m.group("mn"))
    else:
        mon = 6 if end else 7
    return (y, mon) if 1 <= mon <= 12 else None


def _is_city(line: str) -> bool:
    first = re.split(r"[,(]", line)[0].strip()
    return any(first.lower() == c.lower() for c in CITIES) or bool(_URL.search(line)) or \
        bool(re.fullmatch(r"[A-ZА-ЯЁ][\w-]+,\s*(?:Germany|Russia|Россия|USA|Казахстан|Беларусь|Armenia|Serbia|Сербия|"
                          r"Армения|Грузия|Georgia|Cyprus|Кипр|UAE|ОАЭ|Turkey|Турция)", line))


def _is_role(s: str) -> bool:
    return bool(ROLE_RE.search(s))


def _is_org(s: str) -> bool:
    return bool(_ORG_RE.search(s))


def _short(line: str) -> bool:
    return 0 < len(line) <= 90 and not (line.endswith((".", ";")) and len(line.split()) > 4)


def _clean_part(s: str) -> str:
    s = _LABEL_PERIOD.sub("", s.strip())
    s = _EMPLOYMENT_TAIL.sub("", s)
    s = _DURATION_INLINE.sub(" ", s) if _DURATION_INLINE.fullmatch(s.strip()) is None else ""
    s = re.sub(r"\(\s*\)", "", s)
    return s.strip(" \t,;:—–-|·")


def _split_inline(rest: str) -> tuple[str | None, str | None]:
    """«ООО «Ромашка», разработчик» / «Python Developer, Tinkoff» / «Сбер | Data Scientist» → (компания, должность)."""
    rest = _clean_part(rest)
    if not rest:
        return None, None
    m = re.match(r"(.+?)\s+в\s+((?:ООО|АО|ПАО|ЗАО|ИП|компании)\b.*)$", rest)
    parts = [m.group(1), m.group(2)] if m else [p for p in (_clean_part(x) for x in _SEP.split(rest)) if p]
    roles = [p for p in parts if _is_role(p) and not _is_org(p)]
    others = [p for p in parts if p not in roles and not _is_city(p)]
    company = next((p for p in others if _is_org(p)), others[0] if others else None)
    position = ", ".join(roles) if roles else None
    if company is None and position is None and len(parts) == 1:
        return (None, parts[0]) if _is_role(parts[0]) else (parts[0], None)
    return company, position


def _pick(lines: list[str]) -> tuple[str | None, str | None]:
    company = position = None
    for ln in lines:
        lc, lp = _LABEL_COMPANY.match(ln), _LABEL_POSITION.match(ln)
        if lc or lp:
            if lc and not company:
                company = _clean_part(lc.group(1))
            if lp and not position:
                position = _clean_part(lp.group(1))
            continue
        c, p = _split_inline(ln) if (_SEP.search(ln) and not _is_city(ln)) else (None, None)
        if c or p:
            company = company or c
            position = position or p
            continue
        txt = _clean_part(ln)
        if not txt or _is_city(ln):
            continue
        if _is_role(txt) and not _is_org(txt):
            position = position or txt
        elif company is None:
            company = txt
    return company, position


def _section(lines: list[str]) -> tuple[list[str], bool]:
    """Строки раздела опыта; флаг — найден ли заголовок."""
    start = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _EXP_HEAD.match(s) and (len(s) <= 45 or re.match(r"опыт\w*\s+работы\s*[—:–-]", s, re.I)):
            start = i + 1
            break
    if start is None:
        return lines, False
    out = []
    for ln in lines[start:]:
        s = ln.strip()
        if s and len(s) <= 45 and _STOP_HEAD.match(s) and not PERIOD_RE.search(s):
            break
        out.append(ln)
    return out, True


def extract_experience(text: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    lines, has_head = _section([ln.strip() for ln in text.replace("\r", "").split("\n")])
    marks = []
    for i, ln in enumerate(lines):
        m = PERIOD_RE.search(ln)
        if not m:
            continue
        if not has_head and _EDU_WORDS.search(ln):
            continue
        a, b = _parse_date(m.group("a"), False, today), _parse_date(m.group("b"), True, today)
        if not a or not b or (b[0] * 12 + b[1]) < (a[0] * 12 + a[1]) or a[0] > today.year:
            continue
        marks.append((i, m, a, b))
    if not marks:
        return []

    def neighbours_after(i: int, stop: int) -> list[str]:
        got = []
        for ln in lines[i + 1: stop]:
            if not ln:
                if got:
                    break
                continue
            if _BULLET.match(ln) or not _short(ln) or PERIOD_RE.search(ln) or _DESC_LABEL.match(ln):
                break
            if _DURATION_RE.match(ln):
                continue
            got.append(ln)
            if len(got) >= 4:
                break
        return got

    def neighbours_before(i: int, floor: int) -> list[str]:
        got = []
        for ln in reversed(lines[floor:i]):
            if (not ln or _BULLET.match(ln) or not _short(ln) or PERIOD_RE.search(ln) or _DURATION_RE.match(ln)
                    or _DESC_LABEL.match(ln)):
                break
            got.insert(0, ln)
            if len(got) >= 3:
                break
        return got

    first_i = marks[0][0]
    before0 = neighbours_before(first_i, 0)
    layout_before = any(_is_role(x) or _is_org(x) for x in before0 if not _is_city(x))

    entries = []
    for k, (i, m, a, b) in enumerate(marks):
        nxt = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        prev = marks[k - 1][0] + 1 if k else 0
        line = lines[i]
        rest = (line[: m.start()] + " " + line[m.end():]).strip()
        company, position = _split_inline(rest) if rest else (None, None)
        if layout_before:
            # LinkedIn: шапка следующей записи стоит перед её датами — после описания предыдущей
            ctx_before = neighbours_before(i, prev)
            c2, p2 = _pick(ctx_before)
            company, position = company or c2, position or p2
            used_after = []
            if not (company and position):
                used_after = neighbours_after(i, nxt)
                c3, p3 = _pick(used_after)
                company, position = company or c3, position or p3
        else:
            used_after = neighbours_after(i, nxt)
            c2, p2 = _pick(used_after)
            company, position = company or c2, position or p2
        if not (company or position):
            continue
        if not has_head and not position:
            continue  # без заголовка раздела нужна хотя бы должность — иначе это не опыт работы
        # описание: строки записи после шапки до следующей записи (без шапки следующей)
        desc_lines = []
        stop = nxt
        if layout_before and k + 1 < len(marks):
            stop = nxt - len(neighbours_before(nxt, i + 1))
        for ln in lines[i + 1: stop]:
            if not ln or ln in used_after or _DURATION_RE.match(ln) or _is_city(ln):
                continue
            desc_lines.append(_BULLET.sub("", ln))
        current = bool(re.search(_PRESENT, m.group("b"), re.I))
        entries.append({
            "company": (company or "")[:200], "position": (position or "")[:200],
            "period": re.sub(r"\s+", " ", m.group(0).strip()),
            "start": f"{a[0]:04d}-{a[1]:02d}", "end": None if current else f"{b[0]:04d}-{b[1]:02d}", "current": current,
            "description": "\n".join(desc_lines)[:1000],
        })
    return entries[:15]


def years_from_entries(entries: list[dict], today: date | None = None) -> float | None:
    """Стаж по записям: объединение периодов в месяцах (оба конца включительно), пересечения — один раз."""
    today = today or date.today()
    spans = []
    for e in entries:
        try:
            y1, m1 = map(int, (e.get("start") or "").split("-"))
            if e.get("end"):
                y2, m2 = map(int, e["end"].split("-"))
            else:
                y2, m2 = today.year, today.month
        except ValueError:
            continue
        a, b = y1 * 12 + m1, y2 * 12 + m2
        if b >= a:
            spans.append((a, b))
    if not spans:
        return None
    spans.sort()
    total, (cs, ce) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= ce + 1:
            ce = max(ce, e)
        else:
            total += ce - cs + 1
            cs, ce = s, e
    total += ce - cs + 1
    return round(total / 12, 1)
