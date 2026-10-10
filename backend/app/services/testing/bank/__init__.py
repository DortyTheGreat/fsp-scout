"""Реестр шаблонов заданий. Импорт модулей регистрирует шаблоны в TEMPLATES."""
from . import core, data_ops_qa, frontend, python_backend  # noqa: F401
from .base import TEMPLATES, Instance, Template, check_answer

__all__ = ["TEMPLATES", "Template", "Instance", "check_answer", "templates_for"]


def templates_for(spec: str) -> list[Template]:
    return [t for t in TEMPLATES.values() if spec in t.specs]
