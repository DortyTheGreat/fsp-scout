"""Модели хранения. Типы — переносимые (JSON, а не JSONB), чтобы тесты шли и на SQLite;
боевая СУБД — PostgreSQL."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        TypeDecorator, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UTCDateTime(TypeDecorator):
    """Всегда хранит и возвращает aware-datetime в UTC (SQLite теряет tzinfo)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================ пользователи и доступ
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # candidate | employer | admin
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    candidate: Mapped["CandidateProfile | None"] = relationship(back_populates="user", uselist=False,
                                                                cascade="all, delete-orphan", passive_deletes=True)
    company: Mapped["Company | None"] = relationship(back_populates="owner", uselist=False,
                                                     cascade="all, delete-orphan", passive_deletes=True)


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20), default="verify")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Consent(Base):
    """Согласия по 152-ФЗ: на обработку ПДн, на публикацию профиля работодателям, на получение данных ФСП.
    Храним историю (каждое изменение — новая запись) с версией текста согласия."""
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # processing | publication | fsp_data
    granted: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(20), default="2026-10")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class OutboxEmail(Base):
    __tablename__ = "outbox_emails"
    id: Mapped[int] = mapped_column(primary_key=True)
    to: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class AuditLog(Base):
    """Журнал значимых действий: раскрытие контактов, смена грейда, отправка приглашений и т.п."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


# ============================================================ кандидат
DEFAULT_PRIVACY = {
    "show_full_name": False,   # до принятия приглашения работодатель видит «Иван Д.»
    "show_city": True,
    "show_about": True,
    "show_experience": True,
    "show_fsp": True,
    "show_salary": True,
}


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # резюме (самоописание — НЕ влияет на категорию)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    about: Mapped[str] = mapped_column(Text, default="")
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    claimed_skills: Mapped[list] = mapped_column(JSON, default=list)   # slug-и из резюме/анкеты
    roles: Mapped[list] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)       # [{company, position, years, description}]
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_parse_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    # опрос
    direction: Mapped[str | None] = mapped_column(String(60), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    primary_stack: Mapped[str | None] = mapped_column(String(40), nullable=True)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    claimed_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # результат тестирования — именно это определяет категорию, видимую работодателю
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    theta: Mapped[float | None] = mapped_column(Float, nullable=True)
    theta_se: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    skill_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {skill: {score, se, n, evidence}}

    # условия
    salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_formats: Mapped[list] = mapped_column(JSON, default=list)
    relocation: Mapped[bool] = mapped_column(Boolean, default=False)
    open_to_offers: Mapped[bool] = mapped_column(Boolean, default=True)

    # ФСП
    fsp_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    fsp_linked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    fsp_data: Mapped[dict] = mapped_column(JSON, default=dict)   # профиль + достижения (кэш, с подписями)
    fsp_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1, сила подтверждённых достижений

    privacy: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_PRIVACY))
    last_activity_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # «свежесть»
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)  # сгенерирован для демо
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="candidate")

    __table_args__ = (Index("ix_cand_category", "specialization", "grade"),)


class SurveyResponse(Base):
    """История опросов («опрос по отрасли и специализации»)."""
    __tablename__ = "survey_responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    answers: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class GradeHistory(Base):
    __tablename__ = "grade_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(40))
    from_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_grade: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(200))
    attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


# ============================================================ тестирование
class ItemTemplate(Base):
    """Шаблон задания. Генератор — код в app/services/testing/bank (или JSON-тело для черновиков от LLM).
    Здесь — откалиброванные параметры IRT и статистика показов."""
    __tablename__ = "item_templates"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    specializations: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[dict] = mapped_column(JSON, default=dict)        # {skill: вес}
    fmt: Mapped[str] = mapped_column(String(20))                    # single | multi | input | open
    level: Mapped[str] = mapped_column(String(20))                  # экспертная оценка уровня
    a: Mapped[float] = mapped_column(Float)                         # дискриминативность
    b: Mapped[float] = mapped_column(Float)                         # трудность
    c: Mapped[float] = mapped_column(Float, default=0.0)            # угадывание
    status: Mapped[str] = mapped_column(String(20), default="active")  # draft | pretest | active | retired
    source: Mapped[str] = mapped_column(String(20), default="expert")  # expert | llm
    body: Mapped[dict | None] = mapped_column(JSON, nullable=True)     # для шаблонов-черновиков
    time_limit_s: Mapped[int] = mapped_column(Integer, default=120)
    variant_space: Mapped[int] = mapped_column(Integer, default=0)   # различных экземпляров на 200 seed
    exposure_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    calibrated_n: Mapped[int] = mapped_column(Integer, default=0)
    calibrated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class TestAttempt(Base):
    __tablename__ = "test_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="grade")  # grade | confirm | vacancy
    specialization: Mapped[str] = mapped_column(String(40))
    target_grade: Mapped[str] = mapped_column(String(20))
    vacancy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linked_attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ответы которой учитываются
    blueprint: Mapped[dict] = mapped_column(JSON, default=dict)    # {skill: доля} — баланс содержания
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress | finished | abandoned
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    se: Mapped[float] = mapped_column(Float, default=1.0)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)  # passed | failed | needs_confirmation
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    trace: Mapped[list] = mapped_column(JSON, default=list)  # θ/SE после каждого ответа — для графика
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    responses: Mapped[list["ItemResponse"]] = relationship(back_populates="attempt", order_by="ItemResponse.order",
                                                           cascade="all, delete-orphan")


class ItemResponse(Base):
    """Показанный экземпляр задания и ответ. Экземпляр однозначно восстанавливается по (template_id, seed)."""
    __tablename__ = "item_responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[str] = mapped_column(String(80), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # отпечаток экземпляра
    order: Mapped[int] = mapped_column(Integer)
    scored: Mapped[bool] = mapped_column(Boolean, default=True)  # False — калибровочное (претест) задание
    rendered: Mapped[dict] = mapped_column(JSON)    # то, что видит кандидат (без ключа)
    key: Mapped[dict] = mapped_column(JSON)         # правильный ответ — на клиент не отдаётся
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    a: Mapped[float] = mapped_column(Float)
    b: Mapped[float] = mapped_column(Float)
    c: Mapped[float] = mapped_column(Float)
    presented_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    attempt: Mapped[TestAttempt] = relationship(back_populates="responses")


# ============================================================ работодатель
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str | None] = mapped_column(String(40), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_telegram: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    owner: Mapped[User] = relationship(back_populates="company")


class Need(Base):
    """«Потребность» работодателя: кого ищем. На её основе строится подборка."""
    __tablename__ = "needs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(40))
    grades: Mapped[list] = mapped_column(JSON, default=list)
    must_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_skills: Mapped[list] = mapped_column(JSON, default=list)
    work_formats: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_adjacent: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_by: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)


class ShortlistEntry(Base):
    """Подборка (закреплённые кандидаты). Не теряется при смене фильтров."""
    __tablename__ = "shortlist"
    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("needs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    note: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    __table_args__ = (UniqueConstraint("need_id", "candidate_id"),)


class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(40), index=True)
    grade: Mapped[str] = mapped_column(String(20))
    must_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_skills: Mapped[list] = mapped_column(JSON, default=list)
    work_format: Mapped[str] = mapped_column(String(20), default="hybrid")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft | published | closed
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)

    company: Mapped[Company] = relationship()


class Application(Base):
    """Самостоятельный отклик кандидата на вакансию (дополнительный сценарий)."""
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | viewed | accepted | rejected | withdrawn
    reject_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    employer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("vacancy_id", "candidate_id"),)


class Invitation(Base):
    """Приглашение от работодателя — основная механика контакта."""
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[int | None] = mapped_column(ForeignKey("needs.id", ondelete="SET NULL"), nullable=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    work_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_method: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | viewed | accepted | declined | withdrawn
    decline_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decline_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # скор и объяснение в момент отправки
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    viewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    company: Mapped[Company] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()


class StatusEvent(Base):
    """История смены статусов приглашений и откликов (видна обеим сторонам)."""
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))  # invitation | application
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20))
    actor_role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


# ============================================================ регулярные задания
class RegularTask(Base):
    """Короткая задача от работодателя: «реши или предложи подход». Поддерживает свежесть профиля."""
    __tablename__ = "regular_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(String(40))
    skills: Mapped[list] = mapped_column(JSON, default=list)
    min_grade: Mapped[str] = mapped_column(String(20), default="junior")
    rubric: Mapped[list] = mapped_column(JSON, default=list)  # [{criterion, keywords:[...], weight}]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    company: Mapped[Company] = relationship()


class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("regular_tasks.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="offered")  # offered | submitted | skipped | reviewed
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_feedback: Mapped[dict] = mapped_column(JSON, default=dict)
    employer_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    employer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    __table_args__ = (UniqueConstraint("task_id", "candidate_id"),)

    task: Mapped[RegularTask] = relationship()


# ============================================================ модель ранжирования
class RankingModel(Base):
    """Веса ранжирования. Стартуют с экспертных, дообучаются на исходах приглашений (принято/отклонено)."""
    __tablename__ = "ranking_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    weights: Mapped[dict] = mapped_column(JSON)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
