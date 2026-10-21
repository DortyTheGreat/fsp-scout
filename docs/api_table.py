"""Спецификация API и таблица методов для документации: docs/openapi.json и docs/_api_table.md.

    python docs/api_table.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.main import app  # noqa: E402

spec = app.openapi()
(ROOT / "docs" / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

groups: dict[str, list[str]] = {}
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        tag = (op.get("tags") or ["Прочее"])[0]
        codes = ", ".join(sorted(op.get("responses", {}), key=lambda c: (len(c), c)))
        short = path.removeprefix("/api/v1")
        groups.setdefault(tag, []).append(f"| `{method.upper()}` | `{short}` | {op.get('summary', '')} | {codes} |")
out = []
for tag, rows in groups.items():
    out += [f"\n#### {tag}\n", "| Метод | Путь | Назначение | Коды ответов |", "|---|---|---|---|", *rows]
(ROOT / "docs" / "_api_table.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{sum(len(r) for r in groups.values())} методов в {len(groups)} группах")
