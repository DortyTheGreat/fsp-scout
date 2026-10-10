"""Админ-панель: статистика, банк заданий и калибровка, черновики заданий от LLM, модель ранжирования."""
import random
from collections import Counter

import numpy as np
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AUTH_ERRORS, require
from app.core.db import get_db
from app.core.errors import ServiceError, not_found
from app.core.security import utcnow
from app.models import (Application, AuditLog, CandidateProfile, Invitation, ItemResponse, ItemTemplate, OutboxEmail,
                        RankingModel, TestAttempt, User, Vacancy)
from app.services.llm import get_llm
from app.services.matching import ltr
from app.services.matching.ranker import DEFAULT_WEIGHTS, FACTOR_NAMES, FACTORS
from app.services.testing import irt
from app.services.testing import service as testing
from app.services.testing.bank import TEMPLATES
from app.taxonomy import SKILL_BY_SLUG, SPEC_BY_SLUG

router = APIRouter(prefix="/admin", tags=["Администрирование"], responses=AUTH_ERRORS,
                   dependencies=[Depends(require("admin"))])

_variant_cache: dict[str, int] = {}


def variant_space(tid: str, n: int = 200) -> int:
    """Эмпирическое число различных экземпляров шаблона на n случайных seed (по смыслу: текст+код+ответ)."""
    if tid not in _variant_cache and tid in TEMPLATES:
        t = TEMPLATES[tid]
        seen = set()
        for s in range(n):
            i = t.render(s)
            correct = (i.options[i.answer] if i.fmt == "single" else
                       tuple(sorted(i.options[k] for k in i.answer)) if i.fmt == "multi" else tuple(i.answer))
            seen.add((i.prompt, i.code, correct))
        _variant_cache[tid] = len(seen)
    return _variant_cache.get(tid, 1)


@router.get("/stats", summary="Сводная статистика платформы")
def stats(db: Session = Depends(get_db)):
    roles = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    cats = Counter((c.specialization, c.grade) for c in db.scalars(select(CandidateProfile).where(CandidateProfile.grade.is_not(None))))
    attempts = db.scalars(select(TestAttempt).where(TestAttempt.status == "finished")).all()
    inv = Counter(s for (s,) in db.execute(select(Invitation.status)).all())
    answered = inv.get("accepted", 0) + inv.get("declined", 0)
    durations = [(a.finished_at - a.started_at).total_seconds() / 60 for a in attempts if a.finished_at]
    return {
        "users": roles, "candidates_with_category": sum(cats.values()),
        "categories": [{"specialization": k[0], "grade": k[1], "count": v} for k, v in sorted(cats.items())],
        "fsp_linked": db.scalar(select(func.count()).select_from(CandidateProfile).where(CandidateProfile.fsp_id.is_not(None))),
        "tests_finished": len(attempts),
        "tests_passed_share": round(sum(1 for a in attempts if a.outcome == "passed") / len(attempts), 3) if attempts else None,
        "avg_items_per_test": round(float(np.mean([len(a.responses) for a in attempts])), 1) if attempts else None,
        "median_test_minutes": round(float(np.median(durations)), 1) if durations else None,
        "invitations": dict(inv), "invitation_accept_rate": round(inv.get("accepted", 0) / answered, 3) if answered else None,
        "vacancies": db.scalar(select(func.count()).select_from(Vacancy)),
        "applications": db.scalar(select(func.count()).select_from(Application)),
        "templates": dict(Counter(t.status for t in db.scalars(select(ItemTemplate)))),
    }


@router.get("/items", summary="Банк шаблонов заданий с параметрами IRT и статистикой показов")
def items(spec: str | None = None, db: Session = Depends(get_db)):
    rows = db.scalars(select(ItemTemplate).order_by(ItemTemplate.id)).all()
    out = []
    for r in rows:
        if spec and spec not in (r.specializations or []):
            continue
        out.append({"id": r.id, "title": r.title, "specializations": r.specializations,
                    "skills": {s: w for s, w in (r.skills or {}).items()}, "fmt": r.fmt, "level": r.level,
                    "a": round(r.a, 3), "b": round(r.b, 3), "c": round(r.c, 3), "status": r.status, "source": r.source,
                    "exposure_count": r.exposure_count,
                    "p_correct": round(r.correct_count / r.exposure_count, 3) if r.exposure_count else None,
                    "calibrated_n": r.calibrated_n, "variant_space": variant_space(r.id) if r.source == "expert" else 1,
                    "time_limit_s": r.time_limit_s})
    return out


@router.get("/items/{tid}/preview", summary="Экземпляр шаблона с ключом (для экспертной проверки)")
def preview(tid: str, seed: int | None = None, db: Session = Depends(get_db)):
    row = db.get(ItemTemplate, tid)
    if not row:
        raise not_found("Шаблон")
    seed = seed if seed is not None else random.randrange(2 ** 31)
    inst = testing.render(db, tid, seed)
    return {"seed": seed, **inst.public(), **inst.key()}


class DraftIn(BaseModel):
    specialization: str
    skill: str
    level: str = Field("middle", pattern="^(junior|middle|senior)$")
    context: str = Field("", max_length=4000, description="Описание вакансии, под которую нужны задания")


@router.post("/items/draft", status_code=201, summary="Черновик нового задания от LLM (попадает в очередь на ревью)")
def draft(data: DraftIn, db: Session = Depends(get_db)):
    if data.specialization not in SPEC_BY_SLUG or data.skill not in SKILL_BY_SLUG:
        raise ServiceError(422, "bad_input", "Неизвестная специализация или навык")
    llm = get_llm()
    if llm.name == "none":
        raise ServiceError(503, "llm_unavailable", "LLM не подключена (LLM_PROVIDER=none). Черновики можно писать вручную.")
    out = llm.chat_json(
        "Ты — методист технических собеседований. Составь одно задание с выбором одного ответа (4 варианта) "
        "для проверки навыка на заданном уровне. Задание должно проверять понимание, а не память о трюках.",
        f"Навык: {SKILL_BY_SLUG[data.skill].name}. Уровень: {data.level}. Специализация: {SPEC_BY_SLUG[data.specialization].name}.\n"
        f"Контекст вакансии: {data.context}",
        {"title": "string", "prompt": "string", "code": "string|null", "lang": "string|null",
         "options": ["string", "string", "string", "string"], "answer": "integer 0-3", "explanation": "string"})
    if not out or not isinstance(out.get("options"), list) or len(out["options"]) < 3:
        raise ServiceError(502, "llm_bad_output", "LLM вернула некорректный ответ, попробуйте ещё раз")
    tid = f"llm_{data.skill}_{random.randrange(10 ** 6):06d}"
    b0 = {"junior": -0.8, "middle": 0.2, "senior": 1.1}[data.level]
    row = ItemTemplate(id=tid, title=str(out.get("title") or "Черновик LLM")[:200], specializations=[data.specialization],
                       skills={data.skill: 1.0}, fmt="single", level=data.level, a=1.0, b=b0,
                       c=1 / len(out["options"]), status="draft", source="llm",
                       body={k: out.get(k) for k in ("prompt", "code", "lang", "options", "answer", "explanation")})
    db.add(row)
    db.commit()
    return {"id": tid, "status": "draft", "body": row.body}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(draft|pretest|active|retired)$")


@router.post("/items/{tid}/status", summary="Сменить статус шаблона (черновик → претест → рабочий → выведен)")
def set_status(tid: str, data: StatusIn, db: Session = Depends(get_db)):
    row = db.get(ItemTemplate, tid)
    if not row:
        raise not_found("Шаблон")
    if data.status == "active" and row.source == "llm" and row.calibrated_n < 50:
        raise ServiceError(409, "not_calibrated", "Задание от LLM попадает в рабочий банк только после калибровки "
                                                  "(≥ 50 ответов в статусе претеста)")
    row.status = data.status
    db.commit()
    return {"id": tid, "status": row.status}


@router.post("/items/calibrate", summary="Откалибровать претест-задания по накопленным ответам",
             description="Для каждого задания в статусе pretest с ≥ min_n ответов оцениваются (a, b) при известных θ "
                         "отвечавших. Задания с достаточной дискриминативностью (a ≥ 0.5) переводятся в рабочий банк.")
def calibrate(min_n: int = Query(50, ge=10), db: Session = Depends(get_db)):
    report = []
    for row in db.scalars(select(ItemTemplate).where(ItemTemplate.status == "pretest")):
        rs = db.execute(select(ItemResponse, TestAttempt).join(TestAttempt, ItemResponse.attempt_id == TestAttempt.id)
                        .where(ItemResponse.template_id == row.id, ItemResponse.is_correct.is_not(None),
                               TestAttempt.status == "finished")).all()
        if len(rs) < min_n:
            report.append({"id": row.id, "n": len(rs), "status": "недостаточно ответов"})
            continue
        th = np.array([att.theta for _, att in rs])
        u = np.array([1.0 if r.is_correct else 0.0 for r, _ in rs])
        a, b = irt.fit_item_fixed_theta(th, u, row.c, row.a, row.b)
        row.a, row.b, row.calibrated_n, row.calibrated_at = a, b, len(rs), utcnow()
        row.status = "active" if a >= 0.5 else "retired"
        report.append({"id": row.id, "n": len(rs), "a": round(a, 3), "b": round(b, 3), "status": row.status})
    db.commit()
    return report


@router.get("/ranking", summary="Текущие веса ранжирования и история моделей")
def ranking(db: Session = Depends(get_db)):
    models = db.scalars(select(RankingModel).order_by(RankingModel.id.desc())).all()
    return {"default": DEFAULT_WEIGHTS, "factor_names": FACTOR_NAMES,
            "models": [{"id": m.id, "weights": m.weights, "n_samples": m.n_samples, "metrics": m.metrics,
                        "active": m.active, "created_at": m.created_at} for m in models[:10]]}


@router.post("/ranking/train", summary="Дообучить веса на исходах приглашений (принято/отклонено)")
def train(db: Session = Depends(get_db)):
    samples = []
    for i in db.scalars(select(Invitation).where(Invitation.status.in_(("accepted", "declined")))):
        f = (i.match_snapshot or {}).get("features")
        if not f or i.decline_reason == "not_looking":
            continue
        samples.append(({k: f.get(k, 0.0) for k in FACTORS}, 1 if i.status == "accepted" else 0))
    res = ltr.train(samples)
    if res.get("note"):
        return res
    for m in db.scalars(select(RankingModel).where(RankingModel.active.is_(True))):
        m.active = False
    db.add(RankingModel(weights=res["weights"], n_samples=res["n"], metrics={k: v for k, v in res.items() if k != "weights"}))
    db.commit()
    return res


@router.post("/ranking/reset", summary="Вернуть экспертные веса")
def reset(db: Session = Depends(get_db)):
    for m in db.scalars(select(RankingModel).where(RankingModel.active.is_(True))):
        m.active = False
    db.commit()
    return {"weights": DEFAULT_WEIGHTS}


@router.get("/users", summary="Пользователи")
def users(role: str | None = None, db: Session = Depends(get_db), limit: int = Query(100, le=500)):
    q = select(User).order_by(User.id.desc())
    if role:
        q = q.where(User.role == role)
    return [{"id": u.id, "email": u.email, "role": u.role, "verified": u.is_email_verified, "active": u.is_active,
             "created_at": u.created_at} for u in db.scalars(q.limit(limit))]


@router.get("/audit", summary="Журнал действий")
def audit(db: Session = Depends(get_db), limit: int = Query(100, le=500)):
    return [{"id": a.id, "actor": a.actor_user_id, "action": a.action, "target_type": a.target_type,
             "target_id": a.target_id, "meta": a.meta, "at": a.created_at}
            for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))]


@router.get("/outbox", summary="Отправленные письма")
def outbox(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    return [{"id": m.id, "to": m.to, "subject": m.subject, "link": m.link, "at": m.created_at}
            for m in db.scalars(select(OutboxEmail).order_by(OutboxEmail.id.desc()).limit(limit))]
