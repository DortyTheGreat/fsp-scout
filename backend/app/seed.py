"""Генератор демо-данных: `python -m app.seed [--reset] [--candidates 300]`.

Синтетические кандидаты проходят НАСТОЯЩИЙ адаптивный тест (тот же код, что у живых пользователей):
у каждого есть скрытая «истинная» способность по навыкам, ответы симулируются по модели 3PL.
Поэтому у каждой оценки навыка есть реальные доказательства — показанные экземпляры заданий.
История приглашений симулируется скрытой моделью принятия решения кандидатом (для демонстрации
обратной связи и дообучения ранжирования).
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import timedelta

from sqlalchemy import select

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password, utcnow
from app.models import (Application, CandidateProfile, Company, Consent, Invitation, Need, RegularTask, StatusEvent,
                        TaskAssignment, TestAttempt, User, Vacancy)
from app.seed_data import ABOUT, COMPANIES, NEEDS, TASKS, VACANCIES
from app.services.matching import ranker
from app.services.matching.service import parse_need_text
from app.services.testing import irt
from app.services.testing import service as testing
from app.services.testing.bank import TEMPLATES
from app.taxonomy import GRADE_ORDER, SPEC_BY_SLUG, grade_from_theta

PASSWORD = "demo12345"
FIRST_M = ["Александр", "Дмитрий", "Максим", "Иван", "Артём", "Никита", "Михаил", "Егор", "Андрей", "Илья", "Кирилл",
           "Роман", "Павел", "Тимур", "Глеб"]
FIRST_F = ["Анна", "Мария", "Елена", "Дарья", "Алина", "Ксения", "Полина", "София", "Виктория", "Екатерина", "Вера"]
LAST = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
        "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
        "Орлов", "Андреев", "Макаров", "Никитин", "Захаров"]
CITIES = ["Москва"] * 5 + ["Санкт-Петербург"] * 3 + ["Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород",
                                                       "Томск", "Самара", "Иннополис", "Краснодар"]
SPEC_WEIGHTS = {"backend": 34, "frontend": 20, "data_science": 15, "devops": 15, "qa": 16}
SALARY_BASE = {"intern": 60, "junior": 110, "middle": 230, "senior": 380}  # тыс. ₽
SPEC_SALARY_K = {"backend": 1.05, "frontend": 1.0, "data_science": 1.08, "devops": 1.1, "qa": 0.82}


def _user(db, email: str, role: str) -> User:
    u = db.scalars(select(User).where(User.email == email)).first()
    if u:
        return u
    u = User(email=email, password_hash=hash_password(PASSWORD), role=role, is_email_verified=True)
    db.add(u)
    db.flush()
    db.add(Consent(user_id=u.id, kind="processing", granted=True))
    if role == "candidate":
        db.add(Consent(user_id=u.id, kind="publication", granted=True))
    return u


def simulate_test(db, prof: CandidateProfile, target: str, true_skill: dict[str, float], theta: float,
                  rng: random.Random) -> TestAttempt:
    att = testing.start(db, prof, target)
    while att.status == "in_progress":
        cur = testing.current_item(att)
        tpl = TEMPLATES.get(cur.template_id)
        sk = tpl.skills if tpl else {}
        th = (sum(w * true_skill.get(s, theta) for s, w in sk.items()) / sum(sk.values())) if sk else theta
        p = float(irt.prob(th, cur.a, cur.b, cur.c))
        correct = rng.random() < p
        ans = cur.key["answer"]
        if correct:
            value = ans[0] if isinstance(ans, list) and ans and isinstance(ans[0], str) else ans
        else:
            value = "—" if isinstance(ans, list) and ans and isinstance(ans[0], str) else (
                [] if isinstance(ans, list) else (ans + 1) % max(2, len(cur.rendered.get("options") or [1, 2])))
        testing.answer(db, att, cur.id, value)
    return att


def make_candidate(db, rng: random.Random, idx: int, fsp_ids: list[str], fsp_client) -> CandidateProfile | None:
    spec = rng.choices(list(SPEC_WEIGHTS), weights=list(SPEC_WEIGHTS.values()))[0]
    female = rng.random() < 0.3
    first = rng.choice(FIRST_F if female else FIRST_M)
    last = rng.choice(LAST) + ("а" if female else "")
    theta = rng.gauss(0.15, 0.95)
    true_skill = {s: theta + rng.gauss(0, 0.45) for s in SPEC_BY_SLUG[spec].core_skills}
    claimed_grade = grade_from_theta(theta + rng.gauss(0.25, 0.5))  # люди склонны немного переоценивать себя
    if claimed_grade == "intern":
        claimed_grade = "junior"
    u = _user(db, f"cand{idx:04d}@synthetic.demo", "candidate")
    years = {"intern": 0, "junior": rng.uniform(0.3, 1.8), "middle": rng.uniform(1.8, 4.5),
             "senior": rng.uniform(4, 10)}[grade_from_theta(theta)]
    gbase = grade_from_theta(theta)
    sal = SALARY_BASE[gbase] * SPEC_SALARY_K[spec] * rng.uniform(0.85, 1.25)
    core = list(SPEC_BY_SLUG[spec].core_skills)
    prof = CandidateProfile(
        user_id=u.id, full_name=f"{last} {first}", contact_email=u.email, phone=f"+7999{rng.randint(1000000, 9999999)}",
        telegram=f"@{['dev', 'code', 'it', 'eng'][idx % 4]}_{idx}", city=rng.choice(CITIES),
        about=rng.choice(ABOUT[spec]), years_experience=round(years, 1),
        claimed_skills=rng.sample(core, k=min(len(core), rng.randint(3, 6))),
        roles=["individual"] + (["team_lead"] if gbase == "senior" and rng.random() < 0.3 else []),
        soft_skills=rng.sample(["Коммуникация", "Работа в команде", "Самоорганизация", "Наставничество"], 2),
        direction=SPEC_BY_SLUG[spec].direction, specialization=spec, claimed_grade=claimed_grade,
        primary_stack=SPEC_BY_SLUG[spec].stacks[0] if SPEC_BY_SLUG[spec].stacks else None,
        industries=rng.sample(["fintech", "ecommerce", "govtech", "telecom", "edtech", "healthtech"], 2),
        salary_from=int(round(sal, -1)) * 1000, salary_to=int(round(sal * 1.2, -1)) * 1000,
        work_formats=rng.choice([["remote"], ["hybrid", "remote"], ["office", "hybrid"], ["hybrid"], ["office"]]),
        relocation=rng.random() < 0.2, is_synthetic=True, experience=[
            {"company": rng.choice(["ООО «Альфа Софт»", "АО «ДатаСервис»", "ИП Смирнов", "ООО «Облачные решения»"]),
             "position": SPEC_BY_SLUG[spec].name, "period": f"{2026 - max(1, int(years))}—н.в.",
             "description": rng.choice(ABOUT[spec])}] if years >= 0.5 else [])
    db.add(prof)
    db.flush()
    att = simulate_test(db, prof, claimed_grade, true_skill, theta, rng)
    if att.outcome == "failed":
        d = att.decision
        if d.get("can_accept_lower") and d.get("lower_grade") and d["lower_grade"] != "intern":
            testing.accept_lower(db, prof, att)
        elif d.get("lower_grade") and d["lower_grade"] != "intern":
            att2 = simulate_test(db, prof, d["lower_grade"], true_skill, theta, rng)
            if att2.outcome == "failed" and att2.decision.get("can_accept_lower") and att2.decision.get("lower_grade") not in (None, "intern"):
                testing.accept_lower(db, prof, att2)
    # «возраст» профиля: тесты пройдены в разное время
    shift = timedelta(days=rng.choice([rng.randint(1, 30), rng.randint(30, 120), rng.randint(120, 300)]))
    for a in db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == prof.id)):
        a.started_at -= shift
        a.finished_at = (a.finished_at or utcnow()) - shift
        for r in a.responses:
            r.presented_at -= shift
            r.answered_at = (r.answered_at or utcnow()) - shift
    if prof.grade_assigned_at:
        prof.grade_assigned_at -= shift
    prof.last_activity_at = (prof.last_activity_at or utcnow()) - shift
    testing.recompute_skill_scores(db, prof)
    if fsp_client and fsp_ids and rng.random() < 0.45:
        from app.services.fsp.service import load_into_profile
        try:
            load_into_profile(db, prof, fsp_ids.pop(), fsp_client)
        except Exception as e:  # мок недоступен — кандидат остаётся без ФСП
            print("FSP:", e)
    db.commit()
    return prof


def _accept_prob(f: dict, rng: random.Random) -> float:
    """Скрытая модель решения кандидата (для симуляции): деньги и стек важнее, чем думают эксперты."""
    z = 3.2 * f["salary_fit"] + 2.0 * f["skill_fit"] + 1.2 * f["format_fit"] + 0.6 * f["grade_fit"] - 4.0
    return 1 / (1 + math.exp(-z))


def simulate_invitations(db, rng: random.Random, n_per_need: int = 30) -> int:
    created = 0
    from app.services.matching.service import visible_candidates
    cands = [c for c in visible_candidates(db) if c.is_synthetic]  # демо-аккаунты не трогаем
    for need in db.scalars(select(Need)):
        comp = db.get(Company, need.company_id)
        req = ranker.Requirement.from_obj(need)
        ranked = ranker.rank(req, cands, include_adjacent=True)[: n_per_need * 3]
        for row in rng.sample(ranked, min(n_per_need, len(ranked))):
            c, f = row["candidate"], row["features"]
            if db.scalars(select(Invitation).where(Invitation.company_id == comp.id, Invitation.candidate_id == c.id)).first():
                continue
            # вилка приглашения иногда занижена — чтобы отказы по зарплате были в данных
            k = rng.choice([1.0, 1.0, 0.85, 0.7])
            sf, st = int((need.salary_from or 150000) * k), int((need.salary_to or 250000) * k)
            req2 = ranker.Requirement.from_obj(need)
            req2.salary_from, req2.salary_to = sf, st
            f2, d2 = ranker.features(req2, c)
            inv = Invitation(company_id=comp.id, candidate_id=c.id, need_id=need.id, title=need.title,
                             description=need.description or need.title, salary_from=sf, salary_to=st,
                             contact_method=comp.contact_telegram or comp.contact_email or "hr@example.org",
                             match_snapshot={"score": ranker.score(f2), "features": f2,
                                             "explanation": ranker.explain(req2, c, f2, d2)})
            r = rng.random()
            created_at = utcnow() - timedelta(days=rng.randint(1, 40))
            inv.created_at = created_at
            if r < 0.15:
                inv.status = "sent"
            elif r < 0.25:
                inv.status, inv.viewed_at = "viewed", created_at + timedelta(hours=5)
            else:
                inv.viewed_at = created_at + timedelta(hours=3)
                inv.responded_at = created_at + timedelta(days=1)
                if rng.random() < 0.08:
                    inv.status, inv.decline_reason = "declined", "not_looking"
                elif rng.random() < _accept_prob(f2, rng):
                    inv.status = "accepted"
                else:
                    inv.status = "declined"
                    worst = min(("salary_fit", "skill_fit", "format_fit", "grade_fit"), key=lambda k_: f2[k_])
                    inv.decline_reason = {"salary_fit": "salary_low", "skill_fit": "stack_mismatch",
                                          "format_fit": "format_mismatch", "grade_fit": "grade_mismatch"}[worst]
            db.add(inv)
            db.flush()
            for st_ in ["sent"] + (["viewed"] if inv.viewed_at else []) + ([inv.status] if inv.status in ("accepted", "declined") else []):
                db.add(StatusEvent(entity="invitation", entity_id=inv.id, status=st_, actor_role="employer" if st_ == "sent" else "candidate"))
            created += 1
    db.commit()
    return created


def seed(reset: bool, n_candidates: int, seed_value: int = 42) -> None:
    rng = random.Random(seed_value)
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        testing.sync_templates(db)
        if db.scalars(select(User).where(User.email == "admin@demo.ru")).first() and not reset:
            print("Данные уже есть. Используйте --reset для пересоздания.")
            return
        _user(db, "admin@demo.ru", "admin")
        companies = {}
        for c in COMPANIES:
            u = _user(db, c["email"], "employer")
            comp = Company(owner_user_id=u.id, contact_email=c["email"],
                           **{k: v for k, v in c.items() if k != "email"})
            db.add(comp)
            db.flush()
            companies[c["email"]] = comp
        for email, title, text, grade in VACANCIES:
            p = parse_need_text(text)
            db.add(Vacancy(company_id=companies[email].id, title=title, description=text, specialization=p["specialization"],
                           grade=grade, must_skills=p["must_skills"], nice_skills=p["nice_skills"],
                           work_format=(p["work_formats"] or ["hybrid"])[0], city=p["city"] or companies[email].city,
                           salary_from=p["salary_from"] or 150000, salary_to=p["salary_to"] or 250000))
        for email, title, text in NEEDS:
            p = parse_need_text(text)
            db.add(Need(company_id=companies[email].id, title=title, description=text,
                        specialization=p["specialization"], grades=p["grades"], must_skills=p["must_skills"],
                        nice_skills=p["nice_skills"], work_formats=p["work_formats"], city=p["city"],
                        salary_from=p["salary_from"], salary_to=p["salary_to"], parsed_by=p["parsed_by"]))
        for email, title, spec, skills, mg, body, rubric in TASKS:
            db.add(RegularTask(company_id=companies[email].id, title=title, body=body, specialization=spec,
                               skills=skills, min_grade=mg, rubric=rubric))
        db.commit()

        # ФСП: если мок доступен — часть кандидатов получит реальные (синтетические) достижения
        fsp_client, fsp_ids = None, []
        try:
            from app.services.fsp.client import get_fsp_client
            fsp_client = get_fsp_client()
            fsp_client._service_token()
            fsp_ids = [f"FSP-{k:06d}" for k in range(1, 400)]
            rng.shuffle(fsp_ids)
        except Exception as e:
            print(f"Мок ФСП недоступен ({e}); кандидаты будут без достижений ФСП")
            fsp_client = None

        # демо-кандидат без категории
        u = _user(db, "candidate@demo.ru", "candidate")
        db.add(CandidateProfile(user_id=u.id, full_name="Петров Алексей", contact_email=u.email))
        db.commit()
        # демо-senior с ФСП
        rng_demo = random.Random(7)
        u = _user(db, "senior@demo.ru", "candidate")
        prof = CandidateProfile(user_id=u.id, full_name="Демидова Анна", contact_email="anna.demidova@example.org",
                                phone="+79991234567", telegram="@anna_backend", city="Москва", years_experience=5.5,
                                about="Бэкенд на Python 5+ лет: платёжные сервисы, PostgreSQL, очереди. Капитан команды "
                                      "на чемпионатах ФСП по продуктовому программированию.",
                                claimed_skills=["python", "sql", "postgresql", "docker", "web_frameworks", "caching_queues"],
                                roles=["individual", "team_lead", "captain"], soft_skills=["Лидерство", "Коммуникация"],
                                direction="Разработка", specialization="backend", primary_stack="python",
                                claimed_grade="senior", salary_from=320000, salary_to=420000,
                                work_formats=["hybrid", "remote"], industries=["fintech", "ecommerce"],
                                experience=[{"company": "ООО «ФинТехЛаб»", "position": "Senior Python Developer",
                                             "period": "2022—н.в.", "description": "Платёжный шлюз, 2000 RPS, PostgreSQL, Kafka"}])
        db.add(prof)
        db.flush()
        ts = {s: 1.6 + rng_demo.gauss(0, 0.3) for s in SPEC_BY_SLUG["backend"].core_skills}
        for _ in range(3):
            att = simulate_test(db, prof, "senior", ts, 1.6, rng_demo)
            if att.outcome == "passed":
                break
            prof.grade = None
            db.query(TestAttempt).filter(TestAttempt.candidate_id == prof.id).delete()
            db.commit()
        if fsp_client:
            from app.services.fsp.service import load_into_profile
            load_into_profile(db, prof, "FSP-000777", fsp_client)
        db.commit()

        for i in range(n_candidates):
            make_candidate(db, rng, i + 1, fsp_ids, fsp_client)
            if (i + 1) % 50 == 0:
                print(f"  кандидатов: {i + 1}/{n_candidates}")
        n_inv = simulate_invitations(db, rng)
        print(f"  приглашений (история для обратной связи и дообучения): {n_inv}")
        # демо-senior: входящие приглашения и отклик
        demo_emp = companies["employer@demo.ru"]
        need = db.scalars(select(Need).where(Need.company_id == demo_emp.id)).first()
        other = companies["hr@shopflow.demo"]
        for comp, title, sf, st in [(demo_emp, "Senior Python в платёжный шлюз", 360000, 440000),
                                    (other, "Техлид бэкенда маркетплейса", 400000, 500000)]:
            req = ranker.Requirement.from_obj(need)
            f, d = ranker.features(req, prof)
            db.add(Invitation(company_id=comp.id, candidate_id=prof.id, need_id=need.id if comp is demo_emp else None,
                              title=title, description=f"{comp.name}: {comp.description}", salary_from=sf, salary_to=st,
                              contact_method=comp.contact_telegram or comp.contact_email, work_format="hybrid",
                              match_snapshot={"score": ranker.score(f), "features": f, "explanation": ranker.explain(req, prof, f, d)}))
        v = db.scalars(select(Vacancy).where(Vacancy.company_id == demo_emp.id)).first()
        db.add(Application(vacancy_id=v.id, candidate_id=prof.id, cover_letter="Здравствуйте! Интересна задача платёжного шлюза."))
        # регулярные задания для демо-senior
        t = db.scalars(select(RegularTask)).first()
        db.add(TaskAssignment(task_id=t.id, candidate_id=prof.id))
        db.commit()
        print("Готово. Демо-аккаунты (пароль demo12345): candidate@demo.ru, senior@demo.ru, employer@demo.ru, admin@demo.ru")
        _ = GRADE_ORDER


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--candidates", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    seed(a.reset, a.candidates, a.seed)
