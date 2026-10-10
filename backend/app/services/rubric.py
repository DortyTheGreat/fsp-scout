"""Автооценка ответа на регулярное задание по рубрике работодателя (0–10).

Два способа: по ключевым словам критериев (всегда) и LLM (если подключена). Итоговый балл LLM считается
в коде по отметкам «выполнен/нет» и весам критериев, а не берётся из «оценки» модели. Балл — подсказка
работодателю: он видит отметки по критериям и ставит свою оценку.
"""
from __future__ import annotations

import re

from app.services.llm import get_llm

SYSTEM = ("Ты — эксперт-интервьюер. Оцени ответ кандидата по каждому критерию рубрики: выполнен ли он по сути "
          "(met: true/false) и короткий комментарий. Упоминание термина без верного понимания — не выполнен. "
          "Верная мысль своими словами — выполнен. Верни критерии в том же порядке и с теми же номерами.")
SCHEMA = {"criteria": [{"n": "integer — номер критерия", "met": "boolean", "comment": "string"}]}


def keyword_score(rubric: list[dict], answer: str) -> tuple[float, dict]:
    t = answer.lower()
    res, tot, got = [], 0.0, 0.0
    for r in rubric:
        met = any(k.lower() in t for k in r.get("keywords", [])) if r.get("keywords") else False
        res.append({"criterion": r["criterion"], "met": met})
        tot += r.get("weight", 1.0)
        got += r.get("weight", 1.0) if met else 0
    return (round(10 * got / tot, 1) if tot else 0.0), {"method": "keywords", "criteria": res}


def llm_extract(task_body: str, rubric: list[dict], answer: str) -> dict | None:
    llm = get_llm()
    if llm.name == "none" or not rubric:
        return None
    user = (f"Задача:\n{task_body}\n\nРубрика:\n" + "\n".join(f"{i}. {r['criterion']}" for i, r in enumerate(rubric, 1))
            + f"\n\nОтвет кандидата:\n{answer[:6000]}")
    out = llm.chat_json(SYSTEM, user, SCHEMA)
    return out if isinstance(out, dict) else None


def _truthy(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "да", "yes", "1"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("false", "нет", "no", "0"):
        return False
    return None


def from_llm(rubric: list[dict], out: dict | None) -> tuple[float, dict] | None:
    """Балл по отметкам LLM; None — ответ не разобран (тогда работает оценка по ключевым словам)."""
    crit = (out or {}).get("criteria")
    if not isinstance(crit, list) or len(crit) != len(rubric):
        return None
    marks = []
    for i, c in enumerate(crit):
        met = _truthy(c.get("met")) if isinstance(c, dict) else None
        if met is None:
            return None
        marks.append({"criterion": rubric[i]["criterion"], "met": met,
                      "comment": str(c.get("comment") or "")[:300]})
    tot = sum(r.get("weight", 1.0) for r in rubric)
    got = sum(r.get("weight", 1.0) for r, m in zip(rubric, marks) if m["met"])
    return (round(10 * got / tot, 1) if tot else 0.0), {"method": "llm", "criteria": marks}


def auto_score(task_body: str, rubric: list[dict], answer: str) -> tuple[float, dict]:
    if not rubric:
        words = len(re.findall(r"\w+", answer))
        return min(10.0, words / 30), {"method": "length", "note": "рубрика не задана"}
    res = from_llm(rubric, llm_extract(task_body, rubric, answer))
    return res if res is not None else keyword_score(rubric, answer)
