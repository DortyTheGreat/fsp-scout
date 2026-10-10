"""Представления сущностей для API с учётом правил видимости.

Правило ТЗ 2.2: работодатель не видит контактные данные кандидата, пока кандидат не принял
приглашение этой компании или не откликнулся на её вакансию.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, CandidateProfile, Company, Invitation, Need, Vacancy
from app.taxonomy import GRADE_BY_SLUG, SKILL_BY_SLUG, SPEC_BY_SLUG


def contacts_unlocked(db: Session, company_id: int, candidate_id: int) -> bool:
    inv = db.scalars(select(Invitation.id).where(Invitation.company_id == company_id, Invitation.candidate_id == candidate_id,
                                                 Invitation.status == "accepted")).first()
    if inv:
        return True
    app = db.execute(select(Application.id).join(Vacancy, Application.vacancy_id == Vacancy.id)
                     .where(Vacancy.company_id == company_id, Application.candidate_id == candidate_id,
                            Application.status != "withdrawn")).first()
    return bool(app)


def display_name(c: CandidateProfile, unlocked: bool) -> str:
    if unlocked or (c.privacy or {}).get("show_full_name"):
        return c.full_name or f"Кандидат #{c.id}"
    parts = (c.full_name or "").split()
    if len(parts) >= 2:
        return f"{parts[1]} {parts[0][0]}."  # «Иван И.» из «Иванов Иван»
    return f"Кандидат #{c.id}"


def category(c: CandidateProfile) -> dict:
    sp = SPEC_BY_SLUG.get(c.specialization or "")
    g = GRADE_BY_SLUG.get(c.grade or "")
    return {"specialization": c.specialization, "specialization_name": sp.name if sp else None,
            "grade": c.grade, "grade_name": g["name"] if g else None,
            "label": f"{sp.name if sp else '—'} · {g['name'] if g else 'не определён'}"}


def skills_view(c: CandidateProfile, with_evidence: bool = True) -> list[dict]:
    out = []
    fsp_sk = ((c.fsp_data or {}).get("summary") or {}).get("skills", {})
    for s, v in sorted((c.skill_scores or {}).items(), key=lambda kv: -kv[1]["score"]):
        if v.get("n", 0) == 0:
            continue
        d = {"slug": s, "name": SKILL_BY_SLUG[s].name if s in SKILL_BY_SLUG else s, "score": v["score"], "n": v["n"],
             "n_correct": v["n_correct"], "confidence": v["confidence"], "se": v["se"], "fsp_confirmed": s in fsp_sk}
        if with_evidence:
            d["evidence"] = v.get("evidence", [])
            d["fsp_evidence"] = fsp_sk.get(s, {}).get("evidence", [])[:3]
        out.append(d)
    for s, v in fsp_sk.items():  # навыки, подтверждённые только ФСП
        if s in (c.skill_scores or {}) or s not in SKILL_BY_SLUG:
            continue
        out.append({"slug": s, "name": SKILL_BY_SLUG[s].name, "score": None, "n": 0, "fsp_confirmed": True,
                    "fsp_level": v.get("level"), "fsp_evidence": v.get("evidence", [])[:3] if with_evidence else []})
    return out


def fsp_view(c: CandidateProfile, full: bool = True) -> dict:
    data = c.fsp_data or {}
    summ = data.get("summary") or {}
    res = {"linked": bool(c.fsp_id), "fsp_id": c.fsp_id if full else None, "has_history": summ.get("has_history", False),
           "total": summ.get("total", 0), "prizes": summ.get("prizes", 0), "sport_rank": summ.get("sport_rank"),
           "by_discipline": summ.get("by_discipline", {}), "score": summ.get("score", 0)}
    if full:
        res["items"] = [{k: it.get(k) for k in ("id", "event_name", "discipline_name", "level_name", "date", "place",
                                                "participants_total", "is_prize", "team_name", "role", "stack",
                                                "tasks_solved", "tasks_total", "protocol_url", "verified")}
                        for it in sorted(data.get("items", []), key=lambda x: x["date"], reverse=True)]
        res["fetched_at"] = data.get("fetched_at")
    return res


def candidate_for_employer(db: Session, c: CandidateProfile, company: Company, extra: dict | None = None,
                           brief: bool = False) -> dict:
    unlocked = contacts_unlocked(db, company.id, c.id)
    pv = c.privacy or {}
    d = {"id": c.id, "name": display_name(c, unlocked), "category": category(c),
         "theta": c.theta, "grade_assigned_at": c.grade_assigned_at,
         "city": c.city if pv.get("show_city", True) else None,
         "years_experience": c.years_experience if pv.get("show_experience", True) else None,
         "work_formats": c.work_formats, "relocation": c.relocation,
         "salary_from": c.salary_from if pv.get("show_salary", True) else None,
         "salary_to": c.salary_to if pv.get("show_salary", True) else None,
         "skills": skills_view(c, with_evidence=not brief),
         "fsp": fsp_view(c, full=not brief) if pv.get("show_fsp", True) else {"linked": False, "hidden": True},
         "last_activity_at": c.last_activity_at, "contacts_unlocked": unlocked}
    if not brief:
        d.update({"about": c.about if pv.get("show_about", True) else None, "roles": c.roles, "soft_skills": c.soft_skills,
                  "experience": c.experience if pv.get("show_experience", True) else [],
                  "claimed_skills": [{"slug": s, "name": SKILL_BY_SLUG[s].name} for s in (c.claimed_skills or [])
                                     if s in SKILL_BY_SLUG], "education": c.education, "industries": c.industries})
    if unlocked:
        d["contacts"] = {"full_name": c.full_name, "email": c.contact_email, "phone": c.phone, "telegram": c.telegram}
    if extra:
        d.update(extra)
    return d


def company_public(c: Company) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "industry": c.industry, "website": c.website,
            "city": c.city, "size": c.size}


def invitation_view(i: Invitation, for_role: str, db: Session | None = None) -> dict:
    d = {"id": i.id, "title": i.title, "description": i.description, "salary_from": i.salary_from,
         "salary_to": i.salary_to, "work_format": i.work_format, "contact_method": i.contact_method, "status": i.status,
         "decline_reason": i.decline_reason, "decline_comment": i.decline_comment, "created_at": i.created_at,
         "viewed_at": i.viewed_at, "responded_at": i.responded_at, "need_id": i.need_id, "vacancy_id": i.vacancy_id,
         "company": company_public(i.company)}
    if for_role == "employer" and db is not None:
        d["candidate"] = candidate_for_employer(db, i.candidate, i.company, brief=True)
        d["match"] = i.match_snapshot
    if for_role == "candidate":
        d["match_summary"] = (i.match_snapshot or {}).get("explanation", {}).get("summary")
    return d


def vacancy_view(v: Vacancy) -> dict:
    return {"id": v.id, "title": v.title, "description": v.description, "specialization": v.specialization,
            "specialization_name": SPEC_BY_SLUG[v.specialization].name if v.specialization in SPEC_BY_SLUG else None,
            "grade": v.grade, "grade_name": GRADE_BY_SLUG.get(v.grade, {}).get("name"),
            "must_skills": v.must_skills, "nice_skills": v.nice_skills, "work_format": v.work_format, "city": v.city,
            "salary_from": v.salary_from, "salary_to": v.salary_to, "status": v.status, "created_at": v.created_at,
            "updated_at": v.updated_at, "company": company_public(v.company)}


def need_view(n: Need) -> dict:
    return {"id": n.id, "title": n.title, "description": n.description, "specialization": n.specialization,
            "grades": n.grades, "must_skills": n.must_skills, "nice_skills": n.nice_skills, "work_formats": n.work_formats,
            "city": n.city, "salary_from": n.salary_from, "salary_to": n.salary_to, "allow_adjacent": n.allow_adjacent,
            "parsed_by": n.parsed_by, "status": n.status, "created_at": n.created_at, "updated_at": n.updated_at}


def application_view(a: Application, v: Vacancy, for_role: str, db: Session | None = None, cand=None) -> dict:
    d = {"id": a.id, "status": a.status, "cover_letter": a.cover_letter, "reject_reason": a.reject_reason,
         "employer_comment": a.employer_comment, "created_at": a.created_at, "updated_at": a.updated_at,
         "vacancy": {"id": v.id, "title": v.title, "salary_from": v.salary_from, "salary_to": v.salary_to,
                     "company": v.company.name}}
    if for_role == "employer" and db is not None and cand is not None:
        d["candidate"] = candidate_for_employer(db, cand, v.company, brief=True)
        d["match"] = a.match_snapshot
    return d
