"""Резюме: извлечение текста из PDF, разбор в поля (правила + LLM), генерация стандартизированного PDF-профиля.

Разбор резюме — только черновик для анкеты: кандидат видит и правит поля. На категорию резюме не влияет.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from app.services import experience, nlp
from app.services.llm import get_llm
from app.taxonomy import GRADE_BY_SLUG, SKILL_BY_SLUG, SPEC_BY_SLUG

RESUME_SCHEMA = {
    "full_name": "string|null", "email": "string|null", "phone": "string|null", "telegram": "string|null",
    "city": "string|null", "years_experience": "number|null", "grade": "intern|junior|middle|senior|null",
    "specialization": "backend|frontend|data_science|devops|qa|null",
    "skills": ["string — технологии и навыки"], "roles": ["string"], "soft_skills": ["string"],
    "experience": [{"company": "string", "position": "string", "period": "string", "description": "string"}],
    "education": "string|null", "about": "string|null",
}
SYSTEM = ("Ты — модуль разбора резюме ИТ-специалистов. Извлеки факты строго из текста, ничего не придумывай. "
          "Если поля нет в тексте — null или пустой список. skills — все технологии и навыки, которыми кандидат "
          "владеет, как они названы в тексте. specialization — одна из: backend, frontend, data_science (анализ "
          "данных, ML), devops (DevOps, SRE, инфраструктура), qa (тестирование). years_experience — суммарный "
          "коммерческий опыт работы в ИТ в годах (число, пересекающиеся периоды не суммируй).")


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = [(p.extract_text() or "") for p in reader.pages[:10]]
    return "\n".join(parts).strip()


def parse_rules(text: str) -> dict:
    c = nlp.extract_contacts(text)
    jobs = experience.extract_experience(text)
    # стаж: явный итог («Опыт работы — 6 лет 2 месяца») → объединение периодов мест работы (без учёбы и без
    # двойного счёта параллельной работы) → сумма всех диапазонов дат в тексте (старое поведение, запасной путь)
    years = nlp.extract_years_total(text)
    if years is None:
        years = experience.years_from_entries(jobs)
    if years is None:
        years = nlp.extract_years_experience(text)
    return {
        "full_name": nlp.extract_name(text), "email": c["email"], "phone": c["phone"], "telegram": c["telegram"],
        "city": nlp.extract_city(text), "years_experience": years,
        "grade": nlp.extract_grade(text), "specialization": nlp.extract_specialization(text),
        "skills": nlp.extract_skills(text), "roles": nlp.extract_roles(text),
        "soft_skills": nlp.extract_soft_skills(text),
        "experience": [{k: j[k] for k in ("company", "position", "period", "description")} for j in jobs],
        "education": None, "about": None,
    }


_STR_FIELDS = ("full_name", "email", "phone", "telegram", "city", "education", "about")


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[,;\n]", v) if x.strip()]
    return list(v) if isinstance(v, (list, tuple)) else []


def _normalize_llm(d: dict) -> dict:
    """Приводим ответ LLM к справочникам: навыки → slug-и, грейд/специализация → допустимые значения."""
    out = dict(d)
    for k in _STR_FIELDS:
        v = d.get(k)
        out[k] = str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else None
    out["skills"] = list(dict.fromkeys(nlp.extract_skills(" , ".join(map(str, _as_list(d.get("skills")))))))
    out["grade"] = d.get("grade") if d.get("grade") in GRADE_BY_SLUG else None
    out["specialization"] = d.get("specialization") if d.get("specialization") in SPEC_BY_SLUG else None
    try:
        out["years_experience"] = float(d["years_experience"]) if d.get("years_experience") is not None else None
    except (TypeError, ValueError):
        out["years_experience"] = None
    roles = _as_list(d.get("roles"))
    out["roles"] = nlp.extract_roles(" ".join(map(str, roles))) if roles else []
    out["soft_skills"] = nlp.extract_soft_skills(" ; ".join(map(str, _as_list(d.get("soft_skills")))))
    out["experience"] = [{k: str(e.get(k) or "")[:1000] for k in ("company", "position", "period", "description")}
                         for e in _as_list(d.get("experience")) if isinstance(e, dict)][:10]
    return out


def _system_prompt() -> str:
    return SYSTEM + f" Сегодня {date.today():%m.%Y} — от этой даты считай периоды «по настоящее время»."


def llm_extract(text: str) -> dict | None:
    """Сырой ответ LLM; None — LLM выключена, недоступна или ответила не JSON."""
    llm = get_llm()
    if llm.name == "none":
        return None
    out = llm.chat_json(_system_prompt(), text[:12000], RESUME_SCHEMA)
    return out if isinstance(out, dict) else None


def from_llm(llm_out: dict | None) -> dict:
    """Поля только из ответа LLM, без правил (для сравнения методов в validation/llm_compare.py)."""
    norm = _normalize_llm(llm_out or {})
    return {k: norm.get(k) for k in ("full_name", "email", "phone", "telegram", "city", "years_experience", "grade",
                                     "specialization", "skills", "roles", "soft_skills", "experience", "education",
                                     "about")}


def merge(rules: dict, llm_out: dict | None, llm_name: str = "none") -> tuple[dict, dict]:
    """Гибрид, как работает продукт: LLM там, где она ответила, правила — там, где они надёжнее или LLM молчит."""
    if not llm_out:
        return rules, {"method": "rules", "llm": llm_name, "fields": {k: "rules" for k in rules}}
    norm = from_llm(llm_out)
    merged, src = {}, {}
    for k in rules:
        lv, rv = norm.get(k), rules.get(k)
        # контакты — регулярками, стаж — арифметикой дат в коде; остальное — LLM, при пустом ответе — правила
        if k in ("email", "phone", "years_experience") and rv not in (None, ""):
            merged[k], src[k] = rv, "rules"
        elif lv not in (None, "", []):
            merged[k], src[k] = lv, "llm"
        else:
            merged[k], src[k] = rv, "rules"
    merged["skills"] = list(dict.fromkeys((norm.get("skills") or []) + (rules.get("skills") or [])))
    return merged, {"method": "llm+rules", "llm": llm_name, "fields": src}


def parse(text: str) -> tuple[dict, dict]:
    """Возвращает (поля, мета). Мета: каким способом получено каждое поле — для прозрачности и валидации."""
    return merge(parse_rules(text), llm_extract(text), get_llm().name)


# ------------------------------------------------------------------ PDF-профиль
_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def render_profile_pdf(profile, fsp_summary: dict | None, include_contacts: bool = True) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(_FONTS / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FONTS / "DejaVuSans-Bold.ttf")))
    navy, red = colors.HexColor("#2D1451"), colors.HexColor("#FF0053")
    h1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=18, leading=22, textColor=navy)
    h2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=12, leading=16, textColor=navy, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("b", fontName="DejaVu", fontSize=9.5, leading=13)
    muted = ParagraphStyle("m", parent=body, textColor=colors.HexColor("#5b6b8c"))
    esc = lambda s: (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []
    spec = SPEC_BY_SLUG.get(profile.specialization)
    grade = GRADE_BY_SLUG.get(profile.grade or "")
    story.append(Paragraph(esc(profile.full_name or "Кандидат"), h1))
    cat = f"{spec.name if spec else 'Специализация не выбрана'} · {grade['name'] if grade else 'грейд не подтверждён'}"
    story.append(Paragraph(f'<font color="#FF0053">■</font> Категория: <b>{esc(cat)}</b> '
                           f'(подтверждена тестированием платформы)' if grade else esc(cat), body))
    line = [x for x in [profile.city, f"опыт {profile.years_experience:g} г." if profile.years_experience else None,
                        f"ожидания {profile.salary_from or '—'}–{profile.salary_to or '—'} ₽" if profile.salary_from or profile.salary_to else None] if x]
    story.append(Paragraph(esc(" · ".join(line)), muted))
    if include_contacts:
        cts = [x for x in [profile.contact_email, profile.phone, profile.telegram] if x]
        if cts:
            story.append(Paragraph("Контакты: " + esc(", ".join(cts)), body))
    story.append(Spacer(1, 4 * mm))

    if profile.skill_scores:
        story.append(Paragraph("Подтверждённые навыки (по результатам тестирования)", h2))
        rows = [["Навык", "Оценка", "Заданий", "Уверенность"]]
        for s, v in sorted(profile.skill_scores.items(), key=lambda kv: -kv[1]["score"]):
            if v.get("n", 0) == 0:
                continue
            rows.append([SKILL_BY_SLUG[s].name if s in SKILL_BY_SLUG else s, f"{v['score']}/100",
                         f"{v['n_correct']}/{v['n']}", v["confidence"]])
        t = Table(rows, colWidths=[75 * mm, 25 * mm, 25 * mm, 35 * mm])
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "DejaVu", 9), ("FONT", (0, 0), (-1, 0), "DejaVu-Bold", 9),
                               ("TEXTCOLOR", (0, 0), (-1, 0), navy), ("LINEBELOW", (0, 0), (-1, 0), 0.8, red),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fb")])]))
        story.append(t)

    story.append(Paragraph("Достижения ФСП", h2))
    if fsp_summary and fsp_summary.get("has_history"):
        story.append(Paragraph(f"Всего результатов: {fsp_summary['total']}, призовых мест: {fsp_summary['prizes']}"
                               + (f", спортивный разряд: {esc(fsp_summary['sport_rank'])}" if fsp_summary.get("sport_rank") else ""), body))
        for item in (profile.fsp_data or {}).get("items", [])[:8]:
            mark = "✓" if item.get("verified") else "?"
            story.append(Paragraph(f"{mark} {esc(item['date'])} — {esc(item['event_name'])}: место {item['place']} из "
                                   f"{item['participants_total']}" + (f", роль: {esc(item['role'])}" if item.get("role") else ""), body))
    elif profile.fsp_id:
        story.append(Paragraph("Аккаунт ФСП привязан, результатов соревнований пока нет.", muted))
    else:
        story.append(Paragraph("Аккаунт ФСП не привязан.", muted))

    if profile.experience:
        story.append(Paragraph("Опыт работы (со слов кандидата)", h2))
        for e in profile.experience[:6]:
            story.append(Paragraph(f"<b>{esc(e.get('position'))}</b>, {esc(e.get('company'))} — {esc(e.get('period'))}", body))
            if e.get("description"):
                story.append(Paragraph(esc(e["description"])[:600], muted))
    if profile.about:
        story.append(Paragraph("О себе", h2))
        story.append(Paragraph(esc(profile.about)[:1500], body))
    claimed = [SKILL_BY_SLUG[s].name for s in (profile.claimed_skills or []) if s in SKILL_BY_SLUG
               and s not in (profile.skill_scores or {})]
    if claimed:
        story.append(Paragraph("Заявленные навыки (не проверялись тестом)", h2))
        story.append(Paragraph(esc(", ".join(claimed)), muted))
    if profile.soft_skills:
        story.append(Paragraph("Софт-скиллы: " + esc(", ".join(profile.soft_skills)), body))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="Профиль кандидата", author="ФСП Скаут")

    def footer(canvas, d):
        canvas.setFont("DejaVu", 7.5)
        canvas.setFillColor(colors.HexColor("#5b6b8c"))
        canvas.drawString(18 * mm, 10 * mm, "Стандартизированный профиль · ФСП Скаут · категория и оценки навыков "
                                            "получены адаптивным тестированием, достижения подписаны ФСП")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def clean_filename(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name or "profile")[:60]
