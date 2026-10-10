"""Загрузка достижений ФСП в профиль кандидата (общая для привязки, обновления и генератора данных)."""
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models import AuditLog, CandidateProfile, Consent
from app.services.fsp.client import get_fsp_client
from app.services.fsp.scoring import summarize


def load_into_profile(db: Session, p: CandidateProfile, fsp_id: str, client=None) -> dict:
    data = (client or get_fsp_client()).get_achievements(fsp_id)
    items = data["items"]
    summary = summarize(items, data["participant"].get("sport_rank"))
    p.fsp_id = fsp_id
    p.fsp_linked_at = p.fsp_linked_at or utcnow()
    p.fsp_data = {"participant": data["participant"], "items": items, "summary": summary,
                  "fetched_at": utcnow().isoformat()}
    p.fsp_score = summary["score"]
    db.add(Consent(user_id=p.user_id, kind="fsp_data", granted=True))
    db.add(AuditLog(actor_user_id=p.user_id, action="fsp_linked", target_type="candidate", target_id=p.id,
                    meta={"fsp_id": fsp_id, "items": len(items), "verified": sum(1 for i in items if i.get("verified"))}))
    return summary
