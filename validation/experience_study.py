"""Места работы из PDF-резюме: правила, локальная LLM и гибрид на отложенном наборе.

Набор — 40 резюме validation/data/heldout_resumes.json (их писали независимо от кода), разметка мест работы —
validation/data/heldout_experience.json (72 записи в 36 резюме, в 4 резюме опыта нет). Тексты проходят через
PDF так же, как при загрузке в продукте. Ответы LLM берутся из записи прогона llm_compare.py
(validation/out/llm_raw_*.jsonl) — сервер с моделью не нужен.

Совпадение записи: компания и должность совпадают после нормализации (регистр, кавычки, ООО/АО/LLC, пунктуация),
одно может быть частью другого («ООО «НН Софт»» ≈ «НН Софт»). Записи сопоставляются жадно, каждая один раз.

Запуск: python validation/experience_study.py
"""
from __future__ import annotations

import json
import re

from common import OUT, ROOT  # noqa: F401  (настраивает sys.path)
from llm_compare import pdf_roundtrip
from app.services import resume as resume_svc
from app.services.llm import _extract_json

DATA = ROOT / "validation" / "data"
_LEGAL = re.compile(r"\b(?:ооо|оао|зао|пао|ао|ип|llc|inc|ltd|gmbh|corp)\b")


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"'“”„]", " ", s)
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"[^\w#+ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def same(pred: str | None, gold: str) -> bool:
    p = norm(pred)
    if not p:
        return False
    for alt in gold.split("|"):
        g = norm(alt)
        if g and (g in p or p in g):
            return True
    return False


def match(preds: list[dict], golds: list[dict]) -> dict:
    used, both, comp, pos = set(), 0, 0, 0
    for g in golds:
        best, best_k = None, -1
        for j, p in enumerate(preds):
            if j in used:
                continue
            k = 2 * same(p.get("company"), g["company"]) + same(p.get("position"), g["position"])
            if k > best_k:
                best, best_k = j, k
        if best is not None and best_k > 0:
            used.add(best)
            p = preds[best]
            c, ps = same(p.get("company"), g["company"]), same(p.get("position"), g["position"])
            comp += c
            pos += ps
            both += c and ps
    return {"both": both, "company": comp, "position": pos, "n_pred": len(preds), "n_gold": len(golds),
            "first_company": bool(golds) and any(same(p.get("company"), golds[0]["company"]) for p in preds)}


def main():
    resumes = json.loads((DATA / "heldout_resumes.json").read_text(encoding="utf-8"))
    gold = json.loads((DATA / "heldout_experience.json").read_text(encoding="utf-8"))["gold"]
    raw_files = sorted(OUT.glob("llm_raw_*.jsonl"))
    raw = {}
    if raw_files:
        for line in raw_files[0].read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["kind"] == "resume" and r.get("ok"):
                raw[r["id"]] = _extract_json(r["raw"])
    methods = {"before": "Правила до исправления (места работы не извлекались)", "rules": "Правила",
               "llm": "LLM", "hybrid": "Гибрид (как в продукте с моделью)"}
    rows = {m: [] for m in methods}
    examples = []
    for r in resumes:
        text = pdf_roundtrip(r["text"])
        g = gold[r["id"]]
        rules = resume_svc.parse_rules(text)
        lo = raw.get(r["id"])
        preds = {"before": [], "rules": rules["experience"],
                 "llm": resume_svc.from_llm(lo)["experience"] if lo else [],
                 "hybrid": resume_svc.merge(rules, lo)[0]["experience"] if lo else rules["experience"]}
        for m, p in preds.items():
            rows[m].append({"id": r["id"], **match(p, g)})
        if len(examples) < 6 and g:
            examples.append({"id": r["id"], "gold": g[:2], "rules": [{k: e[k] for k in ("company", "position", "period")}
                                                                      for e in rules["experience"][:2]]})
    res = {}
    for m, rs in rows.items():
        n_gold = sum(x["n_gold"] for x in rs)
        n_pred = sum(x["n_pred"] for x in rs)
        both = sum(x["both"] for x in rs)
        with_exp = [x for x in rs if x["n_gold"]]
        without = [x for x in rs if not x["n_gold"]]
        res[m] = {
            "name": methods[m],
            "entries_gold": n_gold, "entries_pred": n_pred,
            "recall": round(both / n_gold, 3) if n_gold else None,
            "precision": round(both / n_pred, 3) if n_pred else None,
            "company_recall": round(sum(x["company"] for x in rs) / n_gold, 3),
            "position_recall": round(sum(x["position"] for x in rs) / n_gold, 3),
            "current_company_filled": round(sum(x["first_company"] for x in with_exp) / len(with_exp), 3),
            "resumes_all_correct": round(sum(x["both"] == x["n_gold"] == x["n_pred"] for x in with_exp) / len(with_exp), 3),
            "no_experience_clean": round(sum(x["n_pred"] == 0 for x in without) / max(1, len(without)), 3),
            "resumes_with_experience": len(with_exp), "resumes_without": len(without),
        }
    out = {"llm_record": raw_files[0].name if raw_files else None, "results": res, "examples": examples}
    (OUT / "experience_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for m, v in res.items():
        print(f"{v['name']:<52} записи P={v['precision']} R={v['recall']}  компания текущего места "
              f"{v['current_company_filled']:.0%}  резюме целиком верно {v['resumes_all_correct']:.0%}")


if __name__ == "__main__":
    main()
