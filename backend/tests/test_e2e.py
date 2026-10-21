"""Сквозной сценарий из ТЗ (п. 3.3): регистрация соискателя → опрос → тест → категория → работодатель
описывает потребность → подборка → приглашение → принятие → раскрытие контактов; плюс отклик на вакансию,
привязка ФСП ID, кулдаун смены грейда и разграничение доступа."""
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import ItemResponse, TestAttempt
from app.main import app


def register_and_login(client: TestClient, email: str, role: str, **extra) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "secret123", "role": role,
                                              "consent_processing": True, "consent_publication": True, **extra})
    assert r.status_code == 201, r.text
    # до подтверждения войти нельзя
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "secret123"}).status_code == 403
    mails = c.get("/api/v1/demo/mailbox", params={"email": email}).json()
    token = parse_qs(urlparse(mails[0]["link"]).query)["token"][0]
    assert c.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200 and r.json()["role"] == role
    return c


def solve_test(c: TestClient, attempt: dict, correct_ratio: float = 1.0) -> dict:
    """Отвечает на задания, подглядывая в ключ в БД (только для автотеста)."""
    n = 0
    while attempt["status"] == "in_progress":
        cur = attempt["current"]
        with SessionLocal() as db:
            key = db.get(ItemResponse, cur["id"]).key
        ans = key["answer"]
        value = ans[0] if isinstance(ans, list) and ans and isinstance(ans[0], str) else ans
        if (n % 10) / 10 >= correct_ratio:
            value = "неверно" if isinstance(value, str) else ([] if isinstance(value, list) else (value + 1) % 4)
        r = c.post(f"/api/v1/tests/{attempt['id']}/answer", json={"item_id": cur["id"], "value": value})
        assert r.status_code == 200, r.text
        attempt = r.json()
        n += 1
        assert n <= 25
    return attempt


def other_cannot_read(client, inv_id: int) -> bool:
    spy = register_and_login(client, "spy@test.ru", "candidate")
    return (spy.get(f"/api/v1/invitations/{inv_id}/messages").status_code == 404
            and spy.post(f"/api/v1/invitations/{inv_id}/messages", json={"text": "привет"}).status_code == 404)


def test_full_flow(client, fsp_mock):
    # ---------------- кандидат
    cand = register_and_login(client, "ivan@test.ru", "candidate", full_name="Иванов Иван")
    assert cand.post("/api/v1/tests/start", json={"target_grade": "middle"}).json()["detail"]["code"] == "survey_required"
    r = cand.post("/api/v1/candidate/survey", json={
        "direction": "Разработка", "specialization": "backend", "primary_stack": "python", "industries": ["fintech"],
        "claimed_grade": "middle", "years_experience": 3, "work_formats": ["remote", "hybrid"],
        "salary_from": 250000, "salary_to": 320000})
    assert r.status_code == 200 and r.json()["recommended_test_grade"] == "middle"
    cand.put("/api/v1/candidate/profile", json={"phone": "+79990001122", "telegram": "@ivan_dev",
                                                 "claimed_skills": ["python", "sql", "docker", "kafka_unknown"]})
    att = cand.post("/api/v1/tests/start", json={"target_grade": "middle"}).json()
    assert att["status"] == "in_progress" and "answer" not in att["current"]  # ключ не уходит на клиент
    att = solve_test(cand, att, 1.0)
    assert att["outcome"] == "passed", att["decision"]
    assert att["decision"]["n_items"] >= 8
    st = cand.get("/api/v1/candidate/status").json()
    assert st["category"]["grade"] == "middle" and st["visible_to_employers"]
    prof = cand.get("/api/v1/candidate/profile").json()
    assert prof["skills"] and all(s["evidence"] for s in prof["skills"] if s["n"])
    # кулдаун: уверенно сдавшему предлагается грейд выше сразу, а вот вниз/повторно — нет
    av = st["availability"]
    assert av["junior"]["allowed"] is False
    assert cand.get("/api/v1/candidate/profile.pdf").headers["content-type"] == "application/pdf"

    # ---------------- привязка ФСП ID (OIDC + PKCE через мок)
    r = cand.get("/api/v1/fsp/link/start", follow_redirects=False)
    assert r.status_code == 302
    auth_url = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(auth_url.query).items()}
    r2 = fsp_mock.post("/realms/fsp/login-actions/authenticate", data={
        "username": "FSP-000777", "password": "demo", "client_id": q["client_id"], "redirect_uri": q["redirect_uri"],
        "state": q["state"], "code_challenge": q["code_challenge"]}, follow_redirects=False)
    cb = urlparse(r2.headers["location"])
    r3 = cand.get(f"/api/v1/fsp/link/callback?{cb.query}", follow_redirects=False)
    assert "fsp=linked" in r3.headers["location"], r3.headers["location"]
    fsp = cand.get("/api/v1/fsp/me").json()
    assert fsp["has_history"] and all(i["verified"] for i in fsp["items"])

    # ---------------- работодатель
    emp = register_and_login(client, "hr@corp.ru", "employer", company_name="ООО Корп")
    parsed = emp.post("/api/v1/employer/needs/parse", json={"text": "Ищем Middle Python-разработчика (бэкенд). "
                      "Стек: Python, SQL, Docker. Будет плюсом: Kubernetes. Вилка 250 000 – 350 000 ₽, удалённо."}).json()
    assert parsed["specialization"] == "backend" and "python" in parsed["must_skills"] and parsed["salary_to"] == 350000
    need = emp.post("/api/v1/employer/needs", json={k: parsed[k] for k in (
        "title", "specialization", "grades", "must_skills", "nice_skills", "work_formats", "salary_from", "salary_to")}
        | {"description": "Платёжный сервис"}).json()
    cats = emp.get(f"/api/v1/employer/needs/{need['id']}/categories").json()
    assert cats[0]["relation"] == "exact" and cats[0]["count"] >= 1
    res = emp.get(f"/api/v1/employer/needs/{need['id']}/candidates").json()
    row = next(x for x in res["items"] if x["id"] == prof["id"])
    assert row["explanation"]["summary"] and "contacts" not in row and row["name"] == "Иван И."
    # закрепили и отфильтровали так, что кандидат не проходит, — он не потерялся
    emp.post(f"/api/v1/employer/needs/{need['id']}/shortlist", json={"candidate_id": prof["id"]})
    res2 = emp.get(f"/api/v1/employer/needs/{need['id']}/candidates", params={"min_score": 101}).json()
    assert res2["total"] == 0 and res2["pinned_hidden"][0]["id"] == prof["id"]
    card = emp.get(f"/api/v1/employer/candidates/{prof['id']}", params={"need_id": need["id"]}).json()
    assert "contacts" not in card and card["fsp"]["has_history"]
    ev_id = card["skills"][0]["evidence"][0]["response_id"]
    ev = emp.get(f"/api/v1/employer/candidates/{prof['id']}/evidence/{ev_id}").json()
    assert ev["prompt"] and ev["is_correct"] is not None
    # приглашение без вилки невозможно
    bad = emp.post("/api/v1/invitations", json={"candidate_id": prof["id"], "title": "Python", "description": "x" * 20,
                                                "contact_method": "hr@corp.ru"})
    assert bad.status_code == 422
    inv = emp.post("/api/v1/invitations", json={
        "candidate_id": prof["id"], "need_id": need["id"], "title": "Middle Python в платежи",
        "description": "Команда платёжного шлюза, highload, Python/PostgreSQL", "salary_from": 280000,
        "salary_to": 340000, "contact_method": "Telegram @corp_hr"}).json()
    assert inv["status"] == "sent" and inv["match"]["score"] > 0
    assert emp.post("/api/v1/invitations", json={
        "candidate_id": prof["id"], "title": "Ещё раз", "description": "x" * 20, "salary_from": 1, "salary_to": 2,
        "contact_method": "x@y.z"}).status_code == 409

    # ---------------- кандидат отвечает
    inbox = cand.get("/api/v1/invitations").json()
    assert inbox[0]["salary_from"] == 280000 and inbox[0]["company"]["name"] == "ООО Корп"
    # до ответа кандидат видит вилку, компанию и способ связи (п. 2.2 ТЗ) и как вилка соотносится с его ожиданиями
    det = cand.get(f"/api/v1/invitations/{inv['id']}").json()
    assert det["status"] == "viewed" and det["contact_method"] == "Telegram @corp_hr"
    assert det["salary_context"]["verdict"] == "covers" and det["salary_context"]["candidate_from"] == 250000
    assert emp.get(f"/api/v1/invitations/{inv['id']}").json()["status"] == "viewed"
    # вопрос до раскрытия контактов: работодатель видит вопрос, но не контакты
    q = cand.post(f"/api/v1/invitations/{inv['id']}/messages", json={"text": "Возможна ли полностью удалённая работа?"})
    assert q.status_code == 201 and q.json()[0]["author_role"] == "candidate"
    e_view = emp.get(f"/api/v1/invitations/{inv['id']}").json()
    assert e_view["messages"][0]["text"].startswith("Возможна") and "contacts" not in e_view["candidate"]
    emp.post(f"/api/v1/invitations/{inv['id']}/messages", json={"text": "Да, команда распределённая"})
    assert [m["author_role"] for m in cand.get(f"/api/v1/invitations/{inv['id']}/messages").json()] == ["candidate", "employer"]
    assert other_cannot_read(client, inv["id"])
    assert cand.post(f"/api/v1/invitations/{inv['id']}/accept").json()["status"] == "accepted"
    card = emp.get(f"/api/v1/employer/candidates/{prof['id']}").json()
    assert card["contacts"]["phone"] == "+79990001122" and card["name"] == "Иванов Иван"

    # ---------------- вакансия и отклик
    vac = emp.post("/api/v1/employer/vacancies", json={
        "title": "Python-разработчик", "description": "Разработка API платёжного сервиса", "specialization": "backend",
        "grade": "middle", "must_skills": ["python", "sql"], "salary_from": 250000, "salary_to": 330000}).json()
    vlist = cand.get("/api/v1/vacancies").json()
    assert vlist["items"][0]["match"]["score"] > 0
    assert cand.post(f"/api/v1/vacancies/{vac['id']}/apply", json={"cover_letter": "Хочу к вам"}).status_code == 201
    assert cand.post(f"/api/v1/vacancies/{vac['id']}/apply", json={}).status_code == 409
    apps = emp.get(f"/api/v1/employer/vacancies/{vac['id']}/applications").json()
    assert apps[0]["status"] == "viewed" and apps[0]["candidate"]["contacts_unlocked"]
    bp = emp.get(f"/api/v1/employer/vacancies/{vac['id']}/test-blueprint").json()
    assert bp["blueprint"] and len({str(i) for i in bp["sample"]["instances"]}) == 3

    # ---------------- разграничение доступа
    other = register_and_login(client, "petr@test.ru", "candidate")
    assert other.get(f"/api/v1/invitations/{inv['id']}").status_code == 404
    assert other.get("/api/v1/employer/needs").status_code == 403
    assert other.get(f"/api/v1/tests/{att['id']}").status_code == 404
    assert other.get("/api/v1/admin/stats").status_code == 403

    # ---------------- аналитика и отзыв согласия
    assert emp.get("/api/v1/employer/insights").json()["accepted"] == 1
    cand.post("/api/v1/auth/consents", json={"kind": "publication", "granted": False})
    res3 = emp.get(f"/api/v1/employer/needs/{need['id']}/candidates").json()
    assert all(x["id"] != prof["id"] for x in res3["items"])


def test_failed_test_and_lower_grade(client):
    c = register_and_login(client, "weak@test.ru", "candidate", full_name="Слабов Олег")
    c.post("/api/v1/candidate/survey", json={"direction": "Разработка", "specialization": "frontend",
                                             "claimed_grade": "senior"})
    att = solve_test(c, c.post("/api/v1/tests/start", json={"target_grade": "senior"}).json(), correct_ratio=0.5)
    assert att["outcome"] == "failed"
    d = att["decision"]
    assert d["lower_grade"] == "middle"
    st = c.get("/api/v1/candidate/status").json()
    assert st["category"]["grade"] is None              # грейд не назначен принудительно
    assert st["availability"]["senior"]["allowed"] is False  # повтор того же грейда — через 14 дней
    assert st["availability"]["middle"]["allowed"] is True   # уровень ниже — сразу
    if d["can_accept_lower"]:
        assert c.post(f"/api/v1/tests/{att['id']}/accept-lower").json()["grade"] == "middle"


def test_abandon_counts_as_wrong(client):
    c = register_and_login(client, "quit@test.ru", "candidate")
    c.post("/api/v1/candidate/survey", json={"direction": "Данные и ИИ", "specialization": "data_science",
                                             "claimed_grade": "junior"})
    att = c.post("/api/v1/tests/start", json={"target_grade": "junior"}).json()
    att2 = c.post("/api/v1/tests/start", json={"target_grade": "junior"}).json()
    assert att2["id"] == att["id"]  # повторный старт возвращает незавершённый тест
    r = c.post(f"/api/v1/tests/{att['id']}/abandon").json()
    assert r["status"] == "finished" and r["decision"]["abandoned"]
    with SessionLocal() as db:
        a = db.get(TestAttempt, att["id"])
        assert all(x.is_correct is False for x in a.responses)
    _ = select


def test_aberrant_pattern_requires_confirmation(client, monkeypatch):
    """Неправдоподобный паттерн ответов: грейд не присваивается до подтверждающего теста
    из шаблонов с богатой вариативностью. Здесь person-fit принудительно занижен — проверяем связку сервиса."""
    from app.services.testing import cat as cat_mod
    c = register_and_login(client, "cheat@test.ru", "candidate")
    c.post("/api/v1/candidate/survey", json={"direction": "Разработка", "specialization": "backend", "claimed_grade": "middle"})
    monkeypatch.setattr(cat_mod, "person_fit", lambda obs, theta: -5.0)
    att = solve_test(c, c.post("/api/v1/tests/start", json={"target_grade": "middle"}).json(), 1.0)
    monkeypatch.undo()
    assert att["outcome"] == "needs_confirmation" and att["decision"]["aberrant"]
    st = c.get("/api/v1/candidate/status").json()
    assert st["category"]["grade"] is None and st["availability"]["middle"].get("confirm")
    conf = c.post("/api/v1/tests/start", json={"target_grade": "middle"}).json()
    assert conf["kind"] == "confirm"
    with SessionLocal() as db:
        from app.models import ItemTemplate
        tid = db.get(ItemResponse, conf["current"]["id"]).template_id
        assert db.get(ItemTemplate, tid).variant_space >= 50  # только шаблоны с богатой вариативностью
    conf = solve_test(c, conf, 1.0)
    assert conf["outcome"] == "passed"
    assert c.get("/api/v1/candidate/status").json()["category"]["grade"] == "middle"


def test_person_fit_flags_inverted_pattern():
    from app.services.testing import cat as cat_mod, irt
    easy = [irt.Obs(1.3, b, 0.0, 0.0) for b in (-1.5, -1.2, -1.0, -0.8, -0.5)]   # лёгкие — неверно
    hard = [irt.Obs(1.3, b, 0.0, 1.0) for b in (0.8, 1.0, 1.2, 1.5, 1.8)]        # трудные — верно
    honest = [irt.Obs(1.3, b, 0.0, 1.0 if b < 0.3 else 0.0) for b in (-1.5, -1.0, -0.5, 0.0, 0.2, 0.5, 1.0, 1.5)]
    st = cat_mod.CatState("middle", {}, obs=easy + hard)
    th, _ = cat_mod.estimate(st)
    assert cat_mod.person_fit(easy + hard, th) < -1.96
    th2, _ = irt.eap(honest)
    assert cat_mod.person_fit(honest, th2) > -1.0
