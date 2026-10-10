"""Конфигурация приложения. Все параметры берутся из переменных окружения (или .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ФСП Скаут"
    # PostgreSQL в docker-compose; для быстрых тестов можно sqlite:///./scout.db
    database_url: str = "postgresql+psycopg://scout:scout@localhost:5432/scout"

    # Безопасность
    secret_key: str = "dev-secret-change-me-please-32-bytes-min"
    access_token_ttl_minutes: int = 60 * 8
    cookie_secure: bool = False  # True за HTTPS
    email_token_ttl_hours: int = 48

    # Демо-режим: письма с подтверждением видны во встроенном «демо-почтовом ящике»,
    # чтобы жюри могло пройти регистрацию без реальной почты. В проде — False + SMTP.
    demo_mode: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@scout.local"

    public_web_url: str = "http://localhost:3000"   # фронтенд (для ссылок в письмах и редиректов)
    public_api_url: str = "http://localhost:3000"   # фронтенд проксирует /api на бэкенд

    # Интеграция с ФСП (мок совместим по URL-схеме с Keycloak: /realms/<realm>/protocol/openid-connect/...)
    fsp_public_url: str = "http://localhost:8001"     # адрес, который видит браузер
    fsp_internal_url: str = "http://localhost:8001"   # адрес внутри docker-сети
    fsp_realm: str = "fsp"
    fsp_client_id: str = "scout"
    fsp_client_secret: str = "scout-secret"

    # LLM: none | openai (любой локальный OpenAI-совместимый сервер: llama.cpp llama-server, Ollama, vLLM, LM Studio)
    llm_provider: str = "none"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:3b"
    llm_api_key: str = "local"
    llm_timeout_s: float = 180.0              # фоновые вызовы: уточнение резюме, оценка ответов
    llm_interactive_timeout_s: float = 45.0   # вызовы, которые ждёт пользователь: разбор потребности
    llm_max_tokens: int = 2048
    llm_disable_thinking: bool = False

    # Механика тестирования
    grade_change_cooldown_days: int = 90     # смена грейда не чаще, чем раз в 90 дней
    same_grade_retry_days: int = 14          # повторная попытка на тот же грейд
    test_min_items: int = 8
    test_max_items: int = 25
    test_confidence_z: float = 1.645         # односторонний 95% интервал для решения о грейде
    pretest_items_per_test: int = 1          # незачётные калибровочные задания в тесте

    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
