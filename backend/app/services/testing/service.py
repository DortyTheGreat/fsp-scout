"""Сервис тестирования: связывает CAT-логику, банк шаблонов и БД; применяет правила смены грейда."""
from __future__ import annotations

import random
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ServiceError
from app.core.security import utcnow
from app.models import (CandidateProfile, GradeHistory, ItemResponse, ItemTemplate, TestAttempt, Vacancy, AuditLog)
from app.services.testing import cat, irt
from app.services.testing.bank import TEMPLATES, check_answer
from app.services.testing.bank.base import Instance
from app.taxonomy import GRADE_BY_SLUG, GRADE_ORDER, SPEC_BY_SLUG, TESTABLE_GRADES, grade_cut

GRACE_S = 20  # запас на сетевые задержки сверх лимита времени задания
FRESH_TRIES = 12  # попыток найти ещё не показанный экземпляр шаблона


def cfg(kind: str = "grade") -> cat.CatConfig:
    c = cat.CatConfig(min_items=settings.test_min_items, max_items=settings.test_max_items, z=settings.test_confidence_z,
                      extend_max_items=settings.test_extend_max_items)
    if kind == "confirm":
        # подтверждающий тест: только шаблоны с практически неисчерпаемыми вариантами — шпаргалка не поможет
        c.min_variants = c.low_variety_threshold
        c.min_items = 6
        c.max_items = 15
        c.extend_max_items = 0
    return c


# ------------------------------------------------------------------ банк в БД
def sync_templates(db: Session) -> int:
    """Регистрирует шаблоны из кода в БД (параметры IRT из кода — стартовые экспертные; после калибровки
    в БД хранятся откалиброванные и код их не перезаписывает)."""
    existing = {t.id: t for t in db.scalars(select(ItemTemplate))}
    added = 0
    for t in TEMPLATES.values():
        row = existing.get(t.id)
        if row is None:
            db.add(ItemTemplate(id=t.id, title=t.title, specializations=list(t.specs), skills=t.skills, fmt=t.fmt,
                                level=t.level, a=t.a, b=t.b, c=t.c, status="active", source="expert",
                                time_limit_s=t.time_limit_s, variant_space=t.variant_space()))
            added += 1
        else:
            row.title, row.specializations, row.skills, row.fmt, row.level = t.title, list(t.specs), t.skills, t.fmt, t.level
            row.time_limit_s = t.time_limit_s
            if not row.variant_space:
                row.variant_space = t.variant_space()
            if row.calibrated_n == 0:
                row.a, row.b, row.c = t.a, t.b, t.c
    for tid, row in existing.items():
        if row.source == "expert" and tid not in TEMPLATES and row.status != "retired":
            row.status = "retired"
    db.commit()
    return added


def pool_for(db: Session, spec: str, statuses=("active",)) -> list[cat.ItemParams]:
    rows = db.scalars(select(ItemTemplate).where(ItemTemplate.status.in_(statuses))).all()
    return [cat.ItemParams(r.id, r.a, r.b, r.c, r.skills, r.status, r.variant_space or 1) for r in rows
            if spec in (r.specializations or [])]


def render(db: Session, template_id: str, seed: int) -> Instance:
    if template_id in TEMPLATES:
        return TEMPLATES[template_id].render(seed)
    row = db.get(ItemTemplate, template_id)  # черновик/претест от LLM: статичное тело + перемешивание вариантов
    body = row.body or {}
    rng = random.Random(seed)
    opts = list(body.get("options", []))
    correct = opts[int(body.get("answer", 0))] if opts else None
    rng.shuffle(opts)
    return Instance(prompt=body.get("prompt", ""), fmt=row.fmt, code=body.get("code"), lang=body.get("lang"),
                    options=opts or None, answer=opts.index(correct) if opts else body.get("answer"),
                    explanation=body.get("explanation", ""))


# ------------------------------------------------------------------ правила старта
def _last_attempt(db: Session, profile: CandidateProfile, target: str | None = None, kind: str = "grade"):
    q = select(TestAttempt).where(TestAttempt.candidate_id == profile.id, TestAttempt.kind == kind,
                                  TestAttempt.status == "finished")
    if target:
        q = q.where(TestAttempt.target_grade == target)
    return db.scalars(q.order_by(TestAttempt.finished_at.desc())).first()


def availability(db: Session, profile: CandidateProfile) -> dict:
    """Какие тесты на грейд можно пройти сейчас и когда откроются остальные."""
    now = utcnow()
    res = {}
    last_any = _last_attempt(db, profile)
    upgrade_window = None
    if last_any and last_any.decision.get("upgrade_suggested") and last_any.finished_at > now - timedelta(days=7):
        upgrade_window = last_any.decision["upgrade_suggested"]
    for g in TESTABLE_GRADES:
        allowed_at = now
        reason = None
        if profile.grade and g != profile.grade and profile.grade_assigned_at and g != upgrade_window:
            t = profile.grade_assigned_at + timedelta(days=settings.grade_change_cooldown_days)
            if t > allowed_at:
                allowed_at, reason = t, f"Грейд можно менять не чаще раза в {settings.grade_change_cooldown_days} дней"
        last_same = _last_attempt(db, profile, g)
        last_any_kind = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == profile.id,
                                                             TestAttempt.target_grade == g, TestAttempt.status == "finished")
                                   .order_by(TestAttempt.finished_at.desc())).first()
        if last_any_kind and last_any_kind.outcome == "needs_confirmation":
            res[g] = {"allowed": True, "allowed_at": now.isoformat(), "reason": None, "confirm": True}
            continue
        if last_same and not (last_same.outcome == "passed" and g != profile.grade):
            t = last_same.finished_at + timedelta(days=settings.same_grade_retry_days)
            if t > allowed_at:
                allowed_at, reason = t, f"Повторная попытка на тот же грейд — через {settings.same_grade_retry_days} дней"
        res[g] = {"allowed": allowed_at <= now, "allowed_at": allowed_at.isoformat(), "reason": reason}
    return res


def start(db: Session, profile: CandidateProfile, target_grade: str, kind: str = "grade",
          vacancy: Vacancy | None = None) -> TestAttempt:
    if not profile.specialization:
        raise ServiceError(409, "survey_required", "Сначала пройдите опрос и выберите специализацию")
    if target_grade not in TESTABLE_GRADES:
        raise ServiceError(422, "bad_grade", "Тест проводится на грейды Junior, Middle, Senior")
    active = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == profile.id,
                                                  TestAttempt.status == "in_progress")).first()
    if active:
        return active  # продолжаем незавершённый тест, а не начинаем новый (нельзя «перебрасывать» неудобные задания)
    spec = vacancy.specialization if vacancy else profile.specialization
    pool = pool_for(db, spec)
    core = list(SPEC_BY_SLUG[spec].core_skills)
    linked = None
    if kind == "grade":
        av = availability(db, profile)[target_grade]
        if not av["allowed"]:
            raise ServiceError(409, "cooldown", av["reason"], allowed_at=av["allowed_at"])
        if av.get("confirm"):
            kind = "confirm"
        blueprint = cat.default_blueprint(core, pool)
        # не сдал грейд выше и сразу проходит тест ниже — ответы той попытки тоже учитываются
        prev = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == profile.id, TestAttempt.kind == "grade",
                                                    TestAttempt.status == "finished", TestAttempt.specialization == spec)
                          .order_by(TestAttempt.finished_at.desc())).first()
        if (kind == "grade" and prev and prev.outcome == "failed" and not (prev.decision or {}).get("abandoned")
                and prev.finished_at > utcnow() - timedelta(days=1)
                and TESTABLE_GRADES.index(prev.target_grade) == TESTABLE_GRADES.index(target_grade) + 1):
            linked = prev.id
    else:
        prev = db.scalars(select(TestAttempt).where(TestAttempt.candidate_id == profile.id,
                                                    TestAttempt.vacancy_id == vacancy.id)).first()
        if prev:
            raise ServiceError(409, "already_taken", "Тест под эту вакансию уже пройден")
        blueprint = cat.blueprint_from_requirements(vacancy.must_skills, vacancy.nice_skills, pool, core)
    attempt = TestAttempt(candidate_id=profile.id, kind=kind, specialization=spec, target_grade=target_grade,
                          vacancy_id=vacancy.id if vacancy else None, blueprint=blueprint, linked_attempt_id=linked)
    db.add(attempt)
    db.flush()
    _present_next(db, attempt)
    db.commit()
    return attempt


# ------------------------------------------------------------------ ход теста
def _state(attempt: TestAttempt, db: Session | None = None) -> cat.CatState:
    st = cat.CatState(target_grade=attempt.target_grade, blueprint=attempt.blueprint or {})
    c = cfg(attempt.kind)
    for r in attempt.responses:
        st.used.append(r.template_id)
        if r.scored and r.is_correct is not None:
            st.obs.append(irt.Obs(r.a, r.b, r.c, 1.0 if r.is_correct else 0.0))
            tpl = TEMPLATES.get(r.template_id)
            for s, w in (tpl.skills if tpl else {}).items():
                st.skill_counts[s] = st.skill_counts.get(s, 0.0) + w
            if tpl and tpl.variant_space() < c.low_variety_threshold:
                st.low_variety_used += 1
    if attempt.linked_attempt_id and db is not None:
        prev = db.get(TestAttempt, attempt.linked_attempt_id)
        if prev:
            st.prior_obs = [irt.Obs(r.a, r.b, r.c, 1.0 if r.is_correct else 0.0) for r in prev.responses
                            if r.scored and r.is_correct is not None]
    return st


def current_item(attempt: TestAttempt) -> ItemResponse | None:
    for r in attempt.responses:
        if r.is_correct is None:
            return r
    return None


def _fresh_instance(db: Session, template_id: str):
    """Свежий экземпляр: из нескольких случайных seed берём тот, чей отпечаток ещё никому не показывался."""
    seed = inst = fp = None
    for _ in range(FRESH_TRIES):
        s_ = secrets.randbits(31)
        i_ = render(db, template_id, s_)
        f_ = i_.fingerprint()
        seed, inst, fp = s_, i_, f_
        if not db.scalars(select(ItemResponse.id).where(ItemResponse.template_id == template_id,
                                                        ItemResponse.fingerprint == f_).limit(1)).first():
            return seed, inst, fp, True
    return seed, inst, fp, False


def _present_next(db: Session, attempt: TestAttempt) -> ItemResponse | None:
    st = _state(attempt, db)
    c = cfg(attempt.kind)
    if cat.should_stop(st, c):
        _finish(db, attempt, st)
        return None
    rng = random.Random(secrets.randbits(32))
    n_pretest = sum(1 for r in attempt.responses if not r.scored)
    item, scored = None, True
    # калибровочное (незачётное) задание: вставляем в случайное место теста, кандидат его не отличит
    if attempt.kind != "confirm" and n_pretest < settings.pretest_items_per_test and st.n >= 2 and rng.random() < 0.25:
        pre = [p for p in pool_for(db, attempt.specialization, ("pretest",)) if p.id not in st.used]
        if pre:
            item, scored = rng.choice(pre), False
    if item is None:
        pool = pool_for(db, attempt.specialization)
        # каждый экземпляр показывается один раз: если у шаблона не нашлось ещё не показанного варианта,
        # он «исчерпан» — берём другой шаблон (до 3 попыток), а не засвеченный вариант
        for _ in range(3):
            item = cat.select_next(st, pool, c, rng)
            if item is None:
                break
            seed, inst, fp, fresh = _fresh_instance(db, item.id)
            if fresh:
                break
            st.used.append(item.id)
    else:
        seed, inst, fp, _ = _fresh_instance(db, item.id)
    if item is None:
        _finish(db, attempt, st)
        return None
    tpl_row = db.get(ItemTemplate, item.id)
    tpl_row.exposure_count += 1
    resp = ItemResponse(attempt_id=attempt.id, template_id=item.id, seed=seed, fingerprint=fp, order=len(attempt.responses) + 1,
                        scored=scored, rendered=inst.public() | {"title": tpl_row.title,
                                                                 "time_limit_s": tpl_row.time_limit_s},
                        key=inst.key(), a=item.a, b=item.b, c=item.c)
    attempt.responses.append(resp)
    db.flush()
    return resp


def answer(db: Session, attempt: TestAttempt, response_id: int, value) -> dict:
    if attempt.status != "in_progress":
        raise ServiceError(409, "finished", "Тест уже завершён")
    cur = current_item(attempt)
    if cur is None or cur.id != response_id:
        raise ServiceError(409, "wrong_item", "Ответ не на текущее задание")
    now = utcnow()
    elapsed = (now - cur.presented_at).total_seconds()
    limit = (cur.rendered or {}).get("time_limit_s", 120)
    timed_out = elapsed > limit + GRACE_S
    cur.response = {"value": value, "timed_out": timed_out}
    cur.is_correct = False if timed_out else check_answer(cur.key, value)
    cur.answered_at = now
    cur.time_ms = int(elapsed * 1000)
    tpl_row = db.get(ItemTemplate, cur.template_id)
    if tpl_row and cur.is_correct:
        tpl_row.correct_count += 1
    st = _state(attempt, db)
    if st.obs:
        theta, se = cat.estimate(st)
        attempt.theta, attempt.se = theta, se
        attempt.trace = list(attempt.trace or []) + [{"n": st.n, "theta": round(theta, 3), "se": round(se, 3)}]
    nxt = _present_next(db, attempt)
    db.commit()
    return {"finished": attempt.status == "finished", "next_item_id": nxt.id if nxt else None,
            "timed_out": timed_out}


def abandon(db: Session, attempt: TestAttempt) -> None:
    """Досрочное завершение: оставшиеся задания засчитываются как неверные — иначе можно было бы
    бросать тест при неудачном начале."""
    if attempt.status != "in_progress":
        return
    cur = current_item(attempt)
    if cur:
        cur.is_correct = False
        cur.response = {"value": None, "abandoned": True}
        cur.answered_at = utcnow()
    st = _state(attempt, db)
    _finish(db, attempt, st, abandoned=True)
    db.commit()


def _finish(db: Session, attempt: TestAttempt, st: cat.CatState, abandoned: bool = False) -> None:
    decision = cat.decide(st, cfg(attempt.kind))
    decision["abandoned"] = abandoned
    attempt.status = "finished"
    attempt.finished_at = utcnow()
    attempt.theta, attempt.se = decision["theta"], decision["se"]
    attempt.outcome = "passed" if decision["passed"] else "failed"
    profile = db.get(CandidateProfile, attempt.candidate_id)
    if attempt.kind == "grade" and decision["aberrant"]:
        # неправдоподобный паттерн ответов (возможна шпаргалка): грейд — только после подтверждающего теста
        attempt.outcome = "needs_confirmation"
        db.add(AuditLog(actor_user_id=profile.user_id, action="aberrant_result", target_type="attempt",
                        target_id=attempt.id, meta={"person_fit": decision["person_fit"]}))
    elif attempt.kind in ("grade", "confirm"):
        if decision["passed"] and profile.grade != attempt.target_grade:
            _set_grade(db, profile, attempt.target_grade, "Тест на грейд пройден", attempt)
            decision["grade_assigned"] = attempt.target_grade
        elif decision["passed"]:
            decision["grade_confirmed"] = attempt.target_grade
        # θ профиля обновляем по последнему тесту на грейд (свежий сигнал для ранжирования)
        if decision["passed"] or profile.grade is None or attempt.target_grade == profile.grade:
            profile.theta, profile.theta_se = attempt.theta, attempt.se
    attempt.decision = decision
    profile.last_activity_at = utcnow()
    db.flush()
    recompute_skill_scores(db, profile)


def _set_grade(db: Session, profile: CandidateProfile, grade: str, reason: str, attempt: TestAttempt | None):
    db.add(GradeHistory(candidate_id=profile.id, specialization=profile.specialization, from_grade=profile.grade,
                        to_grade=grade, reason=reason, attempt_id=attempt.id if attempt else None))
    db.add(AuditLog(actor_user_id=profile.user_id, action="grade_change", target_type="candidate",
                    target_id=profile.id, meta={"from": profile.grade, "to": grade, "reason": reason}))
    profile.grade = grade
    profile.grade_assigned_at = utcnow()


def accept_lower(db: Session, profile: CandidateProfile, attempt: TestAttempt) -> str:
    """Кандидат не прошёл заявленный грейд, но результат уверенно выше порога грейда ниже — он может
    сам принять этот грейд без повторного теста (принудительного понижения нет)."""
    d = attempt.decision or {}
    if attempt.candidate_id != profile.id or attempt.kind != "grade" or not d.get("can_accept_lower"):
        raise ServiceError(409, "not_allowed", "Принять грейд ниже по этому тесту нельзя")
    lower = d["lower_grade"]
    if profile.grade and GRADE_ORDER.index(profile.grade) >= GRADE_ORDER.index(lower):
        raise ServiceError(409, "not_allowed", "Текущий грейд не ниже предложенного")
    _set_grade(db, profile, lower, f"Принят по результату теста на {GRADE_BY_SLUG[attempt.target_grade]['name']}", attempt)
    profile.theta, profile.theta_se = attempt.theta, attempt.se
    d["grade_assigned"] = lower
    attempt.decision = dict(d)
    db.commit()
    return lower


# ------------------------------------------------------------------ оценки по навыкам с доказательствами
def recompute_skill_scores(db: Session, profile: CandidateProfile) -> dict:
    """Оценка каждого навыка = EAP по ответам на задания с этим навыком (все тесты за 365 дней),
    априор центрирован на общем θ кандидата. Каждая оценка сопровождается доказательствами."""
    since = utcnow() - timedelta(days=365)
    rows = db.execute(
        select(ItemResponse, TestAttempt).join(TestAttempt, ItemResponse.attempt_id == TestAttempt.id)
        .where(TestAttempt.candidate_id == profile.id, TestAttempt.status == "finished",
               ItemResponse.scored.is_(True), ItemResponse.is_correct.is_not(None),
               TestAttempt.started_at >= since)
        .order_by(ItemResponse.answered_at.desc())
    ).all()
    titles = {t.id: (t.title, t.level) for t in db.scalars(select(ItemTemplate))}
    per_skill: dict[str, list] = {}
    for resp, att in rows:
        tpl = TEMPLATES.get(resp.template_id)
        skills = tpl.skills if tpl else {}
        for s, w in skills.items():
            per_skill.setdefault(s, []).append((resp, att, w))
    mu = profile.theta if profile.theta is not None else 0.0
    out = {}
    for s, items in per_skill.items():
        obs = [irt.Obs(r.a, r.b, r.c, 1.0 if r.is_correct else 0.0, w) for r, _, w in items]
        th, se = irt.eap(obs, mu=mu, sd=1.0)  # априор вокруг общего θ, но данные навыка весомее
        main = [x for x in items if x[2] >= 0.5]
        out[s] = {
            "score": irt.theta_to_score(th), "theta": round(th, 3), "se": round(se, 3),
            "n": len(main), "n_correct": sum(1 for r, _, _ in main if r.is_correct),
            "confidence": "высокая" if se < 0.45 else ("средняя" if se < 0.65 else "низкая"),
            "source": "test",
            "evidence": [{"response_id": r.id, "attempt_id": a.id, "title": titles.get(r.template_id, ("", ""))[0],
                          "level": titles.get(r.template_id, ("", ""))[1], "correct": bool(r.is_correct),
                          "difficulty": round(r.b, 2), "date": (r.answered_at or a.started_at).date().isoformat()}
                         for r, a, _ in main[:12]],
        }
    profile.skill_scores = out
    db.flush()
    return out


def attempt_public(attempt: TestAttempt, with_items: bool = False) -> dict:
    d = {"id": attempt.id, "kind": attempt.kind, "specialization": attempt.specialization,
         "target_grade": attempt.target_grade, "vacancy_id": attempt.vacancy_id, "status": attempt.status,
         "outcome": attempt.outcome, "theta": attempt.theta, "se": attempt.se, "decision": attempt.decision,
         "trace": attempt.trace, "blueprint": attempt.blueprint, "started_at": attempt.started_at,
         "finished_at": attempt.finished_at,
         "n_answered": sum(1 for r in attempt.responses if r.is_correct is not None),
         "max_items": settings.test_max_items, "min_items": settings.test_min_items}
    if with_items:
        d["items"] = [{"order": r.order, "title": (r.rendered or {}).get("title"), "correct": r.is_correct,
                       "time_ms": r.time_ms} for r in attempt.responses if r.is_correct is not None]
    return d


def grade_cut_value(g: str) -> float:
    return grade_cut(g)
