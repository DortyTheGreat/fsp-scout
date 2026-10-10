"""Отправка писем: всегда пишем в outbox (журнал), при настроенном SMTP — ещё и отправляем."""
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import OutboxEmail

log = logging.getLogger("mailer")


def send(db: Session, to: str, subject: str, body: str, link: str | None = None) -> None:
    db.add(OutboxEmail(to=to, subject=subject, body=body, link=link))
    if not settings.smtp_host:
        log.info("EMAIL to=%s subject=%s link=%s", to, subject, link)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body + (f"\n\n{link}" if link else ""))
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password or "")
            s.send_message(msg)
    except Exception as e:  # письмо не должно ронять бизнес-операцию
        log.warning("SMTP error: %s", e)
