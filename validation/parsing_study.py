"""Валидация разбора текстов: PDF-резюме → поля анкеты и описание потребности → структурированные требования.

Отвечает на вопрос «какой процент людей система разбирает хорошо и сколько нужно ручной проверки».
Резюме генерируются в нескольких непохожих вёрстках с известными («эталонными») полями и прогоняются
через тот же код, что в продукте: pypdf → правила (+ LLM, если задан LLM_PROVIDER).

Запуск: python validation/parsing_study.py            # правила
        LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:3b python validation/parsing_study.py
"""
from __future__ import annotations

import io
import json
import random
from pathlib import Path

from common import OUT  # noqa: F401  (настраивает sys.path)
from app.core.config import settings
from app.services import resume as resume_svc
from app.services.matching.service import parse_need_text
from app.taxonomy import SKILL_BY_SLUG

FIRST = ["Алексей", "Мария", "Дмитрий", "Екатерина", "Иван", "Ольга", "Сергей", "Анна", "Павел", "Наталья", "Артём", "Юлия"]
LAST = ["Смирнов", "Кузнецова", "Попов", "Васильева", "Соколов", "Новикова", "Морозов", "Волкова", "Лебедев", "Козлова"]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Томск"]
SKILL_TEXT = {"python": "Python", "sql": "SQL", "postgresql": "PostgreSQL", "docker": "Docker", "kubernetes": "Kubernetes",
              "git": "Git", "linux": "Linux", "react": "React", "typescript": "TypeScript", "javascript": "JavaScript",
              "html_css": "HTML/CSS", "web_frameworks": "Django", "caching_queues": "Redis", "ci_cd": "GitLab CI",
              "pandas": "pandas", "ml": "scikit-learn", "deep_learning": "PyTorch", "test_automation": "pytest",
              "go": "Golang", "java": "Java", "http_api": "REST API", "monitoring": "Prometheus", "algorithms": "алгоритмы"}
SOFT = {"Работа в команде": "умею работать в команде", "Наставничество": "был ментором для двух стажёров",
        "Лидерство": "руководил командой из 4 человек", "Коммуникация": "коммуникабелен"}


def make_resume(rng: random.Random, layout: int) -> tuple[bytes, dict]:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    fonts = Path(resume_svc.__file__).resolve().parent.parent / "assets" / "fonts"
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts / "DejaVuSans.ttf")))
    i = rng.randrange(len(FIRST))
    female = FIRST[i] in ("Мария", "Екатерина", "Ольга", "Анна", "Наталья", "Юлия")
    last = rng.choice([l for l in LAST if (l.endswith("а") == female)])
    name = f"{last} {FIRST[i]}"
    login = f"user{rng.randint(100, 999)}"
    email = f"{login}@{rng.choice(['mail.ru', 'yandex.ru', 'gmail.com'])}"
    phone_digits = f"9{rng.randint(10, 99)}{rng.randint(1000000, 9999999)}"
    phone_fmt = rng.choice([f"+7 ({phone_digits[:3]}) {phone_digits[3:6]}-{phone_digits[6:8]}-{phone_digits[8:]}",
                            f"8 {phone_digits[:3]} {phone_digits[3:6]} {phone_digits[6:8]} {phone_digits[8:]}"])
    tg = f"@{login}_dev"
    city = rng.choice(CITIES)
    skills = rng.sample(list(SKILL_TEXT), rng.randint(4, 8))
    years = rng.choice([1, 2, 3, 4, 5, 7])
    months = rng.choice([0, 0, 6])
    soft = rng.sample(list(SOFT), rng.randint(0, 2))
    lines = []
    if layout == 0:
        lines = [name, f"{city} · {phone_fmt} · {email} · Telegram: {tg}", "",
                 f"Опыт работы: {years} {'год' if years == 1 else 'года' if years < 5 else 'лет'}" + (f" {months} месяцев" if months else ""),
                 "Навыки: " + ", ".join(SKILL_TEXT[s] for s in skills), "", "О себе: " + "; ".join(SOFT[s] for s in soft)]
    elif layout == 1:
        from datetime import date
        y1, m1 = 2026 - years, rng.randint(1, 12)
        today = date.today()
        dur = ((today.year - y1) * 12 + (today.month - m1)) / 12
        lines = ["РЕЗЮМЕ", name, f"Контакты: {email}, тел. {phone_fmt}", f"Город: {city}", "",
                 "Опыт", f"ООО «Ромашка», разработчик, {m1:02d}.{y1} — настоящее время",
                 "Стек: " + " / ".join(SKILL_TEXT[s] for s in skills), "", "Личные качества: " + ", ".join(SOFT[s] for s in soft), f"tg: {tg}"]
        years, months = round(dur, 1), 0
    else:
        months = 0
        lines = [f"{name}", f"e-mail: {email}", f"phone: {phone_fmt}", f"t.me/{tg[1:]}", f"{city}", "",
                 f"Суммарный опыт — {years} {'год' if years == 1 else 'года' if years < 5 else 'лет'}",
                 "Технологии:"] + [f"- {SKILL_TEXT[s]}" for s in skills] + ["", " ".join(SOFT[s] for s in soft)]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("DejaVu", 11)
    y = 800
    for l in lines:
        c.drawString(50, y, l)
        y -= 18
    c.save()
    gold = {"full_name": name, "email": email, "phone": "+7" + phone_digits, "telegram": tg, "city": city,
            "years_experience": round(years + months / 12, 1), "skills": sorted(skills), "soft_skills": sorted(soft)}
    return buf.getvalue(), gold


def norm_phone(p):
    if not p:
        return None
    d = "".join(ch for ch in p if ch.isdigit())
    if d.startswith("8") and len(d) == 11:
        d = "7" + d[1:]
    return "+" + d


def resume_eval(n: int, seed: int) -> dict:
    rng = random.Random(seed)
    fields = ["full_name", "email", "phone", "telegram", "city", "years_experience"]
    ok = {f: 0 for f in fields}
    tp = fp = fn = 0
    soft_tp = soft_fp = soft_fn = 0
    perfect, method = 0, None
    errors = []
    for k in range(n):
        pdf, gold = make_resume(rng, k % 3)
        text = resume_svc.pdf_to_text(pdf)
        got, meta = resume_svc.parse(text)
        method = meta["method"]
        got_n = dict(got)
        got_n["phone"] = norm_phone(got.get("phone"))
        row_ok = True
        for f in fields:
            g, v = gold[f], got_n.get(f)
            good = (abs((v or -99) - g) <= 0.15) if f == "years_experience" else (str(v or "").lower() == str(g).lower())
            ok[f] += good
            if not good:
                row_ok = False
                if len(errors) < 12:
                    errors.append({"layout": k % 3, "field": f, "gold": g, "got": v})
        gs, ps = set(gold["skills"]), set(got.get("skills") or [])
        tp += len(gs & ps); fp += len(ps - gs); fn += len(gs - ps)
        if gs != ps:
            row_ok = False
        so_g, so_p = set(gold["soft_skills"]), set(got.get("soft_skills") or [])
        soft_tp += len(so_g & so_p); soft_fp += len(so_p - so_g); soft_fn += len(so_g - so_p)
        perfect += row_ok
    prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return {"n": n, "method": method, "llm": settings.llm_provider,
            "field_accuracy": {f: round(v / n, 3) for f, v in ok.items()},
            "skills_precision": round(prec, 3), "skills_recall": round(rec, 3), "skills_f1": round(2 * prec * rec / max(1e-9, prec + rec), 3),
            "soft_skills_f1": round(2 * soft_tp / max(1, 2 * soft_tp + soft_fp + soft_fn), 3),
            "fully_correct_share": round(perfect / n, 3), "needs_review_share": round(1 - perfect / n, 3),
            "error_examples": errors}


NEEDS_GOLD = [
    ("Ищем Middle Python-разработчика в платёжный сервис. Обязательно: Python, PostgreSQL, Docker. Будет плюсом: Kafka. 250 000 – 320 000 ₽, удалённо.",
     {"specialization": "backend", "grades": ["middle"], "must": ["python", "postgresql", "docker"], "nice": ["caching_queues"], "salary": (250000, 320000), "formats": ["remote"]}),
    ("Senior frontend на React и TypeScript, вёрстка, производительность. Москва, офис или гибрид. 350-450 тыс.",
     {"specialization": "frontend", "grades": ["senior"], "must": ["react", "typescript", "html_css"], "nice": [], "salary": (350000, 450000), "formats": ["office", "hybrid"]}),
    ("Junior QA: тест-дизайн, SQL, git. Желательно pytest. до 120 000 руб",
     {"specialization": "qa", "grades": ["junior"], "must": ["test_design", "sql", "git"], "nice": ["test_automation"], "salary": (None, 120000), "formats": []}),
    ("DevOps-инженер (senior): Kubernetes, Terraform, GitLab CI, Prometheus, Linux. Удалённо, от 400к",
     {"specialization": "devops", "grades": ["senior"], "must": ["kubernetes", "ci_cd", "monitoring", "linux", "git"], "nice": [], "salary": (400000, None), "formats": ["remote"]}),
    ("Data Scientist middle: Python, pandas, статистика, CatBoost. Будет плюсом: PyTorch. Гибрид, Санкт-Петербург, 230-300 тыс.",
     {"specialization": "data_science", "grades": ["middle"], "must": ["python", "pandas", "statistics", "ml"], "nice": ["deep_learning"], "salary": (230000, 300000), "formats": ["hybrid"]}),
    ("Нужен бэкендер на Go с опытом от 3 лет: gRPC, PostgreSQL, Redis. 300 000 – 380 000 ₽",
     {"specialization": "backend", "grades": ["middle"], "must": ["go", "http_api", "postgresql", "caching_queues"], "nice": [], "salary": (300000, 380000), "formats": []}),
    ("Стажёр в команду аналитики данных: SQL, Python. Без опыта. 60-80 тыс., офис",
     {"specialization": "data_science", "grades": ["intern"], "must": ["sql", "python"], "nice": [], "salary": (60000, 80000), "formats": ["office"]}),
    ("Ведущий Java-разработчик: Spring Boot, Kafka, микросервисы, PostgreSQL. Вилка 400 000 – 500 000 ₽, гибрид",
     {"specialization": "backend", "grades": ["senior"], "must": ["java", "web_frameworks", "caching_queues", "system_design", "postgresql"], "nice": [], "salary": (400000, 500000), "formats": ["hybrid"]}),
    ("AQA middle: Python, Playwright, REST API, CI/CD. Плюсом будет Docker. 200-260к удалённо",
     {"specialization": "qa", "grades": ["middle"], "must": ["python", "test_automation", "http_api", "ci_cd"], "nice": ["docker"], "salary": (200000, 260000), "formats": ["remote"]}),
    ("Фронтенд-разработчик junior: JavaScript, HTML, CSS, Git. Наставник в команде. 100-140 тыс, Казань, офис",
     {"specialization": "frontend", "grades": ["junior"], "must": ["javascript", "html_css", "git"], "nice": [], "salary": (100000, 140000), "formats": ["office"]}),
]


def need_eval() -> dict:
    spec_ok = grade_ok = sal_ok = fmt_ok = 0
    tp = fp = fn = 0
    rows = []
    for text, g in NEEDS_GOLD:
        p = parse_need_text(text)
        spec_ok += p["specialization"] == g["specialization"]
        grade_ok += p["grades"] == g["grades"]
        sal_ok += (p["salary_from"], p["salary_to"]) == g["salary"]
        fmt_ok += sorted(p["work_formats"]) == sorted(g["formats"])
        gold_sk, got_sk = set(g["must"] + g["nice"]), set(p["must_skills"] + p["nice_skills"])
        tp += len(gold_sk & got_sk); fp += len(got_sk - gold_sk); fn += len(gold_sk - got_sk)
        rows.append({"text": text[:60], "spec": p["specialization"], "grades": p["grades"], "salary": [p["salary_from"], p["salary_to"]],
                     "missed_skills": sorted(gold_sk - got_sk), "extra_skills": sorted(got_sk - gold_sk)})
    n = len(NEEDS_GOLD)
    prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return {"n": n, "method": p.get("parsed_by"), "specialization_acc": round(spec_ok / n, 3), "grade_acc": round(grade_ok / n, 3),
            "salary_acc": round(sal_ok / n, 3), "formats_acc": round(fmt_ok / n, 3),
            "skills_precision": round(prec, 3), "skills_recall": round(rec, 3), "rows": rows}


def main():
    res = {"resume": resume_eval(150, 5), "needs": need_eval()}
    suffix = "" if settings.llm_provider == "none" else f"_{settings.llm_provider}"
    (OUT / f"parsing_results{suffix}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    _ = SKILL_BY_SLUG


if __name__ == "__main__":
    main()
