"""Разбор опыта работы правилами: место работы, должность, период — в разных вёрстках резюме.

Тексты здесь — наш набор для разработки (dev). Итоговая проверка — на отложенном наборе, который писали
независимо от кода (validation/data/heldout_resumes.json, разметка мест работы — heldout_experience.json).
"""
from datetime import date

import pytest

from app.services.experience import extract_experience, years_from_entries

TODAY = date(2026, 10, 1)

HH = """Иванов Пётр
Опыт работы — 5 лет 1 месяц

Сентябрь 2021 — настоящее время
5 лет 1 месяц
ООО «Северный Код»
Москва, sevcode.ru
Ведущий Go-разработчик
— Проектирование сервиса биллинга
— Наставничество

Февраль 2019 — Август 2021
2 года 7 месяцев
Банк «Звезда»
Казань
Java-разработчик
— Поддержка АБС

Образование
Высшее
2018
Казанский федеральный университет
"""

INLINE = """Резюме
Опыт
ООО «Ромашка», разработчик, 03.2021 — настоящее время
Стек: Python / Django
Личные качества: ответственность
"""

LINKEDIN = """Anna Smirnova
Experience
Senior Backend Engineer
Acme Corp · Full-time
Jan 2021 - Present · 4 yrs 10 mos
Berlin, Germany
- Built payment APIs in Go
Backend Developer
Globex LLC
Mar 2018 - Dec 2020 · 2 yrs 10 mos
- Django services
Education
Moscow State University, 2013 - 2017
"""

FREEFORM = """Кратко обо мне: бэкенд на Go.
Где работал:
2019–2022 — Яндекс, бэкенд-разработчик (Go)
2022–н.в. — Т-Банк, старший разработчик
Курсы: 2018 Яндекс Практикум
"""

PAREN = """Work history
Python Developer, Tinkoff (2020 — 2023)
QA Engineer, Kaspersky Lab (2017 — 2020)
"""

PIPES = """ОПЫТ РАБОТЫ
Сбер | Data Scientist | 09.2021 – 05.2024
Лаборатория анализа данных | Младший аналитик | 11/2019 – 08/2021
НАВЫКИ
Python, SQL
"""

HEADER_BEFORE = """Трудовая деятельность
АО «Альфа-Технологии»
QA-инженер
с 05.2019 по 08.2021
Автоматизация тестов на pytest.

ИП Сидоров
Тестировщик
с 09.2017 по 04.2019
Ручное тестирование.

Образование
2013–2017 ТГУ, прикладная математика
"""

OVERLAP = """Опыт работы
Июнь 2018 — Декабрь 2021 (3 года 7 месяцев)
ООО «Логистик Плюс», Санкт-Петербург
Системный администратор / DevOps
Январь 2020 — Июнь 2022
Фриланс
DevOps-консультант
"""


def _pairs(entries):
    return [(e["company"], e["position"]) for e in entries]


def test_hh_export():
    e = extract_experience(HH, TODAY)
    assert _pairs(e) == [("ООО «Северный Код»", "Ведущий Go-разработчик"), ("Банк «Звезда»", "Java-разработчик")]
    assert e[0]["current"] and e[0]["start"] == "2021-09"
    assert e[1]["end"] == "2021-08"
    assert "биллинга" in e[0]["description"]


def test_inline_line():
    e = extract_experience(INLINE, TODAY)
    assert _pairs(e) == [("ООО «Ромашка»", "разработчик")]
    assert e[0]["current"]


def test_linkedin_english():
    e = extract_experience(LINKEDIN, TODAY)
    assert _pairs(e) == [("Acme Corp", "Senior Backend Engineer"), ("Globex LLC", "Backend Developer")]
    assert e[1]["start"] == "2018-03" and e[1]["end"] == "2020-12"


def test_freeform_dash():
    e = extract_experience(FREEFORM, TODAY)
    assert _pairs(e) == [("Яндекс", "бэкенд-разработчик (Go)"), ("Т-Банк", "старший разработчик")]


def test_position_comma_company_parens():
    e = extract_experience(PAREN, TODAY)
    assert _pairs(e) == [("Tinkoff", "Python Developer"), ("Kaspersky Lab", "QA Engineer")]


def test_pipes():
    e = extract_experience(PIPES, TODAY)
    assert _pairs(e) == [("Сбер", "Data Scientist"), ("Лаборатория анализа данных", "Младший аналитик")]


def test_header_before_dates_and_education_ignored():
    e = extract_experience(HEADER_BEFORE, TODAY)
    assert _pairs(e) == [("АО «Альфа-Технологии»", "QA-инженер"), ("ИП Сидоров", "Тестировщик")]
    # учёба 2013–2017 в стаж не попадает: 09.2017–08.2021 = 4 года
    assert years_from_entries(e, TODAY) == pytest.approx(4.0, abs=0.1)


def test_overlap_not_double_counted():
    e = extract_experience(OVERLAP, TODAY)
    assert _pairs(e) == [("ООО «Логистик Плюс»", "Системный администратор / DevOps"), ("Фриланс", "DevOps-консультант")]
    # 06.2018–06.2022 без двойного счёта пересечения = 4 года
    assert years_from_entries(e, TODAY) == pytest.approx(4.0, abs=0.1)


def test_no_experience_section():
    assert extract_experience("Иван Иванов\nНавыки: Python, SQL\nОбразование: МГУ, 2015–2019", TODAY) == []


KEYVALUE = """Опыт работы
Компания: ООО «Дельта Софт»
Должность: Frontend-разработчик
Период работы: 01.2022 — 09.2024
Обязанности: React, TypeScript
Компания: Студия «Пиксель»
Должность: Верстальщик
Период работы: 06.2020 — 12.2021
"""

NO_BLANKS_HH = """Опыт работы — 3 года
Март 2023 — настоящее время
3 года 8 месяцев
Ozon
Москва
Middle Python developer
— Сервис рекомендаций
Январь 2021 — Февраль 2023
2 года 2 месяца
ООО «Код Плюс»
Junior Python-разработчик
— Внутренние сервисы
"""

AT_AND_V = """Experience
Senior Developer at Acme, 2019 – 2021
Разработчик в ООО «Ромашка» (2016–2019)
"""


def test_key_value_labels():
    e = extract_experience(KEYVALUE, TODAY)
    assert _pairs(e) == [("ООО «Дельта Софт»", "Frontend-разработчик"), ("Студия «Пиксель»", "Верстальщик")]


def test_hh_without_blank_lines():
    e = extract_experience(NO_BLANKS_HH, TODAY)
    assert _pairs(e) == [("Ozon", "Middle Python developer"), ("ООО «Код Плюс»", "Junior Python-разработчик")]


def test_at_and_v():
    e = extract_experience(AT_AND_V, TODAY)
    assert _pairs(e) == [("Acme", "Senior Developer"), ("ООО «Ромашка»", "Разработчик")]


def test_pdf_upload_fills_workplaces_without_llm(client):
    """Ошибка из экспертизы: при загрузке PDF место работы не заполнялось (правила опыт не извлекали)."""
    from tests.test_e2e import register_and_login
    from tests.test_llm_paths import _pdf
    c = register_and_login(client, "pdf-exp@test.ru", "candidate")
    r = c.post("/api/v1/candidate/resume", files={"file": ("cv.pdf", _pdf(HH), "application/pdf")})
    assert r.status_code == 200, r.text
    assert [e["company"] for e in r.json()["parsed"]["experience"]] == ["ООО «Северный Код»", "Банк «Звезда»"]
    prof = c.get("/api/v1/candidate/profile").json()
    assert prof["experience"][0]["position"] == "Ведущий Go-разработчик"
    assert prof["experience"][0]["period"].startswith("Сентябрь 2021")
    # кандидат правит и сохраняет; слишком длинные поля отклоняются валидацией
    prof["experience"][0]["position"] = "Тимлид"
    r = c.put("/api/v1/candidate/profile", json={"experience": prof["experience"][:1]})
    assert r.status_code == 200 and r.json()["experience"][0]["position"] == "Тимлид"
    assert c.put("/api/v1/candidate/profile", json={"experience": [{"company": "x" * 300}]}).status_code == 422
