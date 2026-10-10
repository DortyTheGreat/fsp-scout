"""Пути с LLM без настоящей модели: подставной провайдер возвращает заданный JSON (или мусор)."""
import pytest

from app.services import llm as llm_mod
from app.services import resume as resume_svc
from app.services import rubric as rubric_svc
from app.services.matching import service as matching


class FakeLLM:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply

    def chat_json(self, system, user, schema=None, timeout_s=None):
        return self.reply

    def chat(self, system, user, timeout_s=None):
        return None


@pytest.fixture
def use_llm():
    def _set(reply):
        llm_mod.set_llm(FakeLLM(reply))
    yield _set
    llm_mod.set_llm(None)


RESUME = """Петров Илья Сергеевич
г. Тюмень, +7 (912) 345-67-89, ilya.petrov@mail.ru, tg: @ilya_dev
Опыт работы — 3 года 2 месяца. Python, FastAPI, PostgreSQL, Docker."""


def test_extract_json_handles_think_and_fences():
    assert llm_mod._extract_json('<think>hmm {"a": 2}</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert llm_mod._extract_json("not json") is None


def test_resume_hybrid_prefers_rules_for_contacts_and_years(use_llm):
    use_llm({"full_name": "Петров Илья Сергеевич", "email": "wrong@x.ru", "phone": None, "city": "Тюмень",
             "years_experience": 5, "specialization": "backend", "skills": "Python, FastAPI, Kafka"})
    fields, meta = resume_svc.parse(RESUME)
    assert meta["method"] == "llm+rules"
    assert fields["full_name"] == "Петров Илья Сергеевич" and fields["city"] == "Тюмень"
    assert fields["email"] == "ilya.petrov@mail.ru" and meta["fields"]["email"] == "rules"
    assert fields["years_experience"] == pytest.approx(3.2, abs=0.05)
    assert {"python", "web_frameworks", "caching_queues", "postgresql", "docker"} <= set(fields["skills"])
    only = resume_svc.from_llm({"full_name": ["bad"], "skills": "Python", "years_experience": "abc"})
    assert only["full_name"] is None and only["skills"] == ["python"] and only["years_experience"] is None


def test_resume_falls_back_to_rules_on_bad_llm_output(use_llm):
    use_llm(None)
    fields, meta = resume_svc.parse(RESUME)
    assert meta["method"] == "rules" and fields["email"] == "ilya.petrov@mail.ru"


def test_need_llm_normalization_and_merge(use_llm):
    out = {"specialization": "qa", "grades": ["senior", "middle", "lead"], "must_skills": ["Python", "Playwright"],
           "nice_skills": ["Docker", "Python"], "salary_from": "250", "salary_to": 320000, "work_formats": "remote",
           "city": None}
    only = matching.need_from_llm(out)
    assert only["grades"] == ["middle", "senior"]
    assert only["must_skills"] == ["python", "test_automation"] and only["nice_skills"] == ["docker"]
    assert (only["salary_from"], only["salary_to"]) == (250000, 320000) and only["work_formats"] == ["remote"]
    use_llm(out)
    res = matching.parse_need_text("Ищем AQA, г. Казань. Python, Playwright. Docker будет плюсом. 250–320 тыс.")
    assert res["parsed_by"] == "llm" and res["specialization"] == "qa"
    assert res["city"] == "Казань"  # LLM промолчала — город из правил
    use_llm(None)
    assert matching.parse_need_text("Ищем Python-разработчика")["parsed_by"] == "rules"


def test_rubric_llm_score_uses_weights_and_falls_back():
    rubric = [{"criterion": "индекс", "keywords": ["индекс"], "weight": 2.0},
              {"criterion": "EXPLAIN", "keywords": ["explain"], "weight": 1.0}]
    score, fb = rubric_svc.from_llm(rubric, {"criteria": [{"n": 1, "met": True}, {"n": 2, "met": "false"}]})
    assert score == pytest.approx(6.7) and fb["method"] == "llm"
    assert rubric_svc.from_llm(rubric, {"criteria": [{"met": True}]}) is None  # не тот размер — не верим
    score, fb = rubric_svc.auto_score("Задача", rubric, "Посмотрю EXPLAIN и добавлю составной индекс")
    assert fb["method"] == "keywords" and score == 10.0


def _pdf(text: str) -> bytes:
    import io
    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    fonts = Path(resume_svc.__file__).resolve().parent.parent / "assets" / "fonts"
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts / "DejaVuSans.ttf")))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("DejaVu", 10)
    for i, line in enumerate(text.split("\n")):
        c.drawString(40, 800 - 14 * i, line)
    c.save()
    return buf.getvalue()


def test_resume_upload_refined_by_llm_in_background(client, use_llm):
    from test_e2e import register_and_login

    from app.api import candidate as cand_api
    from app.core.db import SessionLocal
    from app.models import CandidateProfile

    c = register_and_login(client, "bg-resume@test.ru", "candidate")
    text = "Dmitry Sokolov\nTyumen, d.sokolov@mail.ru, +7 916 482 35 17\n4 years: Python, FastAPI, Kafka"
    use_llm({"full_name": "Dmitry Sokolov", "city": "Тюмень", "years_experience": 4, "specialization": "backend",
             "skills": ["Python", "FastAPI", "Kafka"], "about": "x" * 6000})
    r = c.post("/api/v1/candidate/resume", files={"file": ("cv.pdf", _pdf(text), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["llm_status"] == "pending" and r.json()["meta"]["method"] == "rules"
    prof = c.get("/api/v1/candidate/profile").json()  # фоновая задача TestClient уже выполнилась
    meta = prof["resume_parse_meta"]
    assert meta["llm_status"] == "done" and meta["method"] == "llm+rules"
    assert prof["full_name"] == "Dmitry Sokolov" and prof["city"] == "Тюмень"
    assert prof["contact_email"] == "bg-resume@test.ru"  # заполненное поле разбор не трогает
    assert len(prof["about"]) == 5000  # обрезано до лимита формы
    assert {"python", "web_frameworks", "caching_queues"} <= set(prof["claimed_skills"])

    # правка кандидата, сделанная пока модель думала, не перезаписывается
    with SessionLocal() as db:
        p = db.scalar(select_profile(prof))
        p.city = "Екатеринбург"
        p.resume_parse_meta = meta | {"token": "t2", "applied": {"city": "Тюмень"}, "llm_status": "pending"}
        db.commit()
        pid = p.id
    use_llm({"city": "Москва", "full_name": "Dmitry Sokolov"})
    cand_api.refine_resume_with_llm(pid, "t2")
    with SessionLocal() as db:
        p = db.get(CandidateProfile, pid)
        assert p.city == "Екатеринбург" and p.resume_parse_meta["llm_status"] == "done"
    cand_api.refine_resume_with_llm(pid, "stale-token")  # устаревшая задача ничего не делает


def select_profile(prof):
    from sqlalchemy import select

    from app.models import CandidateProfile
    return select(CandidateProfile).where(CandidateProfile.id == prof["id"])


def test_task_answer_scored_by_keywords_then_llm(client, use_llm):
    from test_e2e import register_and_login

    from app.core.db import SessionLocal
    from app.models import CandidateProfile, Company, RegularTask, TaskAssignment, User

    c = register_and_login(client, "bg-task@test.ru", "candidate")
    pid = c.get("/api/v1/candidate/profile").json()["id"]
    with SessionLocal() as db:
        owner = db.query(User).filter(User.email == "bg-task@test.ru").one()
        comp = Company(owner_user_id=owner.id, name="Тест")  # владельцем для теста выступает тот же пользователь
        db.add(comp)
        db.flush()
        t = RegularTask(company_id=comp.id, title="Медленный запрос", body="Ускорьте запрос", specialization="backend",
                        rubric=[{"criterion": "Индекс", "keywords": ["индекс"], "weight": 2.0},
                                {"criterion": "EXPLAIN", "keywords": ["explain"], "weight": 1.0}])
        db.add(t)
        db.flush()
        a = TaskAssignment(task_id=t.id, candidate_id=pid)
        db.add(a)
        db.commit()
        asg = a.id
    use_llm({"criteria": [{"n": 1, "met": True}, {"n": 2, "met": True}]})
    r = c.post(f"/api/v1/tasks/{asg}/submit", json={"answer": "Добавлю составной индекс по двум полям и проверю план."})
    assert r.status_code == 200, r.text
    assert r.json()["auto_feedback"]["method"] == "keywords" and r.json()["auto_feedback"]["llm_status"] == "pending"
    assert r.json()["auto_score"] == pytest.approx(6.7)
    row = next(x for x in c.get("/api/v1/tasks").json() if x["id"] == asg)
    assert row["auto_feedback"]["method"] == "llm" and row["auto_feedback"]["llm_status"] == "done"
    assert row["auto_score"] == 10.0
