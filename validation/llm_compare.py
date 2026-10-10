"""Сравнение разбора текстов и автооценки заданий: правила, локальная LLM и гибрид (как работает продукт).

Набор — validation/data/heldout_*.json: 40 резюме, 40 описаний потребностей, 4 задания × 8 ответов с
эталонной разметкой. Набор составлен отдельно от правил: у автора не было доступа к словарю синонимов и коду
разбора, а правила после первого прогона на нём не подстраивались. Резюме идут тем же путём, что в продукте:
текст → PDF → извлечение текста pypdf → разбор.

Каждый текст отправляется в модель ОДИН раз, из ответа считаются два метода:
  «LLM»    — только ответ модели, приведённый к справочникам (если ответ не разобран — пустой результат);
  «Гибрид» — как в продукте: LLM там, где она ответила, правила там, где надёжнее или модель промолчала.

Запуск из корня проекта:
  python validation/llm_compare.py --rules-only        только правила, модель не нужна
  python validation/llm_compare.py                     llama.cpp llama-server на http://127.0.0.1:8080
  python validation/llm_compare.py --base-url http://127.0.0.1:11434 --model qwen2.5:3b     Ollama
  --quick   10 резюме, 10 потребностей, 8 ответов (примерно вчетверо быстрее)
На Windows — compare-llm.bat в корне проекта. Ctrl+C останавливает прогон, метрики считаются по уже
обработанным текстам (тексты разных типов идут вперемешку, поэтому частичный прогон тоже показателен).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "validation" / "data"
OUT = ROOT / "validation" / "out"

RESUME_FIELDS = {"full_name": "ФИО", "email": "Email", "phone": "Телефон", "telegram": "Telegram", "city": "Город",
                 "years_experience": "Стаж (±0,5 года)", "specialization": "Специализация"}


# ------------------------------------------------------------------ аргументы и окружение
def parse_args():
    p = argparse.ArgumentParser(description="Правила vs локальная LLM на отложенном наборе текстов")
    p.add_argument("--base-url", default="http://127.0.0.1:8080",
                   help="адрес OpenAI-совместимого сервера (llama-server: http://127.0.0.1:8080, Ollama: http://127.0.0.1:11434)")
    p.add_argument("--model", help="имя модели из GET /v1/models; без него — выбор из списка")
    p.add_argument("--rules-only", action="store_true", help="только правила, без модели")
    p.add_argument("--quick", action="store_true", help="короткий прогон: 10 + 10 + 8 текстов")
    p.add_argument("--timeout", type=float, default=300, help="таймаут одного запроса, с (по умолчанию 300)")
    p.add_argument("--allow-thinking", action="store_true",
                   help="не отключать режим рассуждений у моделей вроде Qwen3 (медленнее)")
    p.add_argument("--yes", action="store_true", help="ничего не спрашивать (для запуска без консоли)")
    return p.parse_args()


def setup_env(args) -> None:
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ["LLM_PROVIDER"] = "none"  # модель подставляется явно через set_llm
    os.environ["LLM_DISABLE_THINKING"] = "false" if args.allow_thinking else "true"
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ask(prompt: str, default: str, args) -> str:
    if args.yes or not sys.stdin.isatty():
        return default
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    return v or default


def norm_base(url: str) -> str:
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://", url):
        url = "http://" + url
    if not re.search(r"/v\d+$", url):
        url += "/v1"
    return url


# ------------------------------------------------------------------ сервер и модель
def list_models(base: str) -> list[dict]:
    import httpx
    r = httpx.get(base + "/models", timeout=10)
    r.raise_for_status()
    d = r.json()
    items = (d.get("data") or d.get("models") or []) if isinstance(d, dict) else d
    out, seen = [], set()
    for e in items:
        if not isinstance(e, dict):
            continue
        mid = e.get("id") or e.get("model") or e.get("name")
        st = e.get("status")
        st = st.get("value") if isinstance(st, dict) else st
        if mid and mid not in seen:
            seen.add(mid)
            out.append({"id": mid, "status": st})
    return out


def connect(args) -> tuple[str, list[dict]] | None:
    base = norm_base(args.base_url)
    while True:
        try:
            models = list_models(base)
            if models:
                return base, models
            print(f"Сервер {base} отвечает, но не сообщил ни одной модели.")
        except Exception as e:
            print(f"Сервер {base} не отвечает ({type(e).__name__}).")
        print("Запустите llama-server (или Ollama) и проверьте адрес. Пример: llama-server -m model.gguf --port 8080")
        v = ask("Адрес сервера (Enter — попробовать снова, q — выход): ", "", args)
        if args.yes or v.lower() == "q":
            return None
        if v:
            base = norm_base(v)


def choose_model(models: list[dict], args, exclude: set[str]) -> str | None:
    if args.model and not exclude:
        return args.model
    left = [m for m in models if m["id"] not in exclude]
    if not left:
        return None
    if len(left) == 1 and not exclude:
        return left[0]["id"]
    print("\nМодели на сервере:")
    for i, m in enumerate(left, 1):
        print(f"  {i}. {m['id']}" + (f"  [{m['status']}]" if m.get("status") else ""))
    loaded = next((i for i, m in enumerate(left, 1) if m.get("status") == "loaded"), 1)
    if exclude:
        v = ask("Сравнить ещё одну? Номер модели (Enter — выход): ", "", args)
        if not v:
            return None
    else:
        v = ask(f"Номер модели [Enter — {loaded}]: ", str(loaded), args)
    try:
        return left[int(v) - 1]["id"]
    except (ValueError, IndexError):
        print("Нет такого номера.")
        return None


def make_llm(base: str, model: str, timeout: float):
    from app.services.llm import OpenAICompatLLM

    class MeasuredLLM(OpenAICompatLLM):
        """Тот же клиент, что в продукте, плюс запись сырого ответа, времени и скорости генерации."""

        def __init__(self):
            super().__init__(base_url=base, model=model, timeout_s=timeout)
            self.last: dict = {}

        def _complete(self, messages, json_mode, timeout_s=None):
            t0 = time.perf_counter()
            rec: dict = {"ok": False}
            try:
                resp = self._post(messages, json_mode)  # в сравнении — общий таймаут --timeout
                content = resp["choices"][0]["message"]["content"]
                rec.update(ok=True, raw=content, usage=resp.get("usage"), timings=resp.get("timings"))
                return content
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:300]
                return None
            finally:
                rec["seconds"] = round(time.perf_counter() - t0, 2)
                self.last = rec

    return MeasuredLLM()


# ------------------------------------------------------------------ данные
def load_data(quick: bool) -> dict:
    resumes = json.loads((DATA / "heldout_resumes.json").read_text(encoding="utf-8"))
    needs = json.loads((DATA / "heldout_needs.json").read_text(encoding="utf-8"))
    tasks = json.loads((DATA / "heldout_tasks.json").read_text(encoding="utf-8"))
    answers = [{"task": t, **a} for t in tasks for a in (t["answers"][:2] if quick else t["answers"])]
    if quick:
        resumes, needs = resumes[:10], needs[:10]
    return {"resume": resumes, "need": needs, "answer": answers}


def pdf_roundtrip(text: str) -> str:
    """Текст → PDF (A4, перенос строк) → pypdf, как при загрузке резюме в продукте."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    from app.services import resume as resume_svc
    fonts = ROOT / "backend" / "app" / "assets" / "fonts"
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts / "DejaVuSans.ttf")))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("DejaVu", 10)
    y = 800
    for para in text.split("\n"):
        for line in textwrap.wrap(para, 95) or [""]:
            if y < 50:
                c.showPage()
                c.setFont("DejaVu", 10)
                y = 800
            c.drawString(40, y, line)
            y -= 14
    c.save()
    return resume_svc.pdf_to_text(buf.getvalue())


def interleave(data: dict) -> list[tuple[str, int]]:
    jobs, n = [], max(len(v) for v in data.values())
    for i in range(n):
        for kind in ("resume", "need", "answer"):
            if i < len(data[kind]):
                jobs.append((kind, i))
    return jobs


# ------------------------------------------------------------------ сравнение с эталоном
def _n(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower().replace("ё", "е")).strip(" .,;:")


def phone_norm(p) -> str | None:
    d = re.sub(r"\D", "", str(p or ""))
    if len(d) == 11 and d[0] in "78":
        d = "7" + d[1:]
    elif len(d) == 10:
        d = "7" + d
    return "+" + d if d else None


def tg_norm(t) -> str | None:
    t = re.sub(r"^(https?://)?(www\.)?(t\.me/|telegram\.me/)", "", _n(t)).lstrip("@")
    return t or None


def city_norm(c) -> str:
    return re.sub(r"^(г\.|город)\s*", "", _n(c))


def resume_field_ok(field: str, g: dict, p: dict) -> bool:
    v = p.get(field)
    if field == "full_name":
        toks = lambda s: sorted(re.findall(r"[a-zа-я-]+", _n(s)))  # noqa: E731
        return bool(v) and toks(g["full_name"]) == toks(v)
    if field == "email":
        return _n(v) == _n(g["email"]) if g["email"] else not v
    if field == "phone":
        return phone_norm(v) == g["phone"] if g["phone"] else not phone_norm(v)
    if field == "telegram":
        return tg_norm(v) == tg_norm(g["telegram"]) if g["telegram"] else not tg_norm(v)
    if field == "city":
        if not g["city"]:
            return not v
        return bool(v) and city_norm(v) in {city_norm(x) for x in [g["city"], *g.get("city_aliases", [])]}
    if field == "years_experience":
        if g["years_experience"] is None:
            return v is None
        try:
            return v is not None and abs(float(v) - g["years_experience"]) <= 0.5
        except (TypeError, ValueError):
            return False
    if field == "specialization":
        return v == g["specialization"]
    raise KeyError(field)


def skill_counts(gold: list, optional: list, pred: list) -> tuple[int, int, int]:
    g, o, p = set(gold), set(optional), set(pred or [])
    return len(g & p), len(p - g - o), len(g - p)


def prf(tp: int, fp: int, fn: int) -> dict:
    pr, rc = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(2 * pr * rc / max(1e-9, pr + rc), 3)}


def eval_resumes(items: list[dict], preds: list[dict]) -> dict:
    ok = {f: 0 for f in RESUME_FIELDS}
    tp = fp = fn = 0
    all_ok = 0
    errors = []
    for it, p in zip(items, preds):
        g = it["gold"]
        row = True
        for f in RESUME_FIELDS:
            good = resume_field_ok(f, g, p)
            ok[f] += good
            row &= good
            if not good and len(errors) < 25:
                errors.append({"id": it["id"], "field": f, "gold": g.get(f), "got": p.get(f)})
        a, b, c = skill_counts(g["skills"], g.get("skills_optional", []), p.get("skills"))
        tp, fp, fn = tp + a, fp + b, fn + c
        all_ok += row
    n = max(1, len(items))
    return {"n": len(items), "fields": {f: round(v / n, 3) for f, v in ok.items()},
            "all_fields_ok": round(all_ok / n, 3), "skills": prf(tp, fp, fn), "errors": errors}


def eval_needs(items: list[dict], preds: list[dict]) -> dict:
    c = {"specialization": 0, "grades_exact": 0, "grades_overlap": 0, "salary": 0, "formats": 0, "city": 0}
    tp = fp = fn = 0
    placed = placed_ok = 0
    errors = []
    for it, p in zip(items, preds):
        g = it["gold"]
        pg = sorted(p.get("grades") or [])
        acc = [sorted(x) for x in g.get("grades_acceptable") or []] + [sorted(g["grades"])]
        res = {"specialization": p.get("specialization") == g["specialization"],
               "grades_exact": pg in acc,
               "grades_overlap": bool(set(pg) & set(g["grades"])),
               "salary": (p.get("salary_from"), p.get("salary_to")) == (g["salary_from"], g["salary_to"]),
               "formats": set(p.get("work_formats") or []) == set(g["work_formats"]),
               "city": (city_norm(p.get("city")) == city_norm(g["city"])) if g["city"] else not p.get("city")}
        for k, v in res.items():
            c[k] += v
            if not v and len(errors) < 25:
                errors.append({"id": it["id"], "field": k, "gold": {"specialization": g["specialization"], "grades_exact": g["grades"],
                               "grades_overlap": g["grades"], "salary": [g["salary_from"], g["salary_to"]],
                               "formats": g["work_formats"], "city": g["city"]}[k],
                               "got": {"specialization": p.get("specialization"), "grades_exact": pg, "grades_overlap": pg,
                                       "salary": [p.get("salary_from"), p.get("salary_to")],
                                       "formats": p.get("work_formats"), "city": p.get("city")}[k]})
        gold_all = g["must"] + g["nice"]
        pred_must, pred_nice = list(p.get("must_skills") or []), list(p.get("nice_skills") or [])
        a, b, d = skill_counts(gold_all, g.get("skills_optional", []), pred_must + pred_nice)
        tp, fp, fn = tp + a, fp + b, fn + d
        for s in set(pred_must + pred_nice) & set(gold_all):
            placed += 1
            placed_ok += (s in pred_must) == (s in g["must"])
    n = max(1, len(items))
    return {"n": len(items), **{k: round(v / n, 3) for k, v in c.items()}, "skills": prf(tp, fp, fn),
            "must_nice_placement": round(placed_ok / max(1, placed), 3), "errors": errors}


def eval_answers(items: list[dict], preds: list[tuple[float, list[bool]]]) -> dict:
    agree = total = 0
    tp = fp = fn = tn = 0
    abs_err = 0.0
    for it, (score, marks) in zip(items, preds):
        rubric, gm = it["task"]["rubric"], it["gold_met"]
        tot = sum(r.get("weight", 1.0) for r in rubric)
        gold_score = 10 * sum(r.get("weight", 1.0) for r, m in zip(rubric, gm) if m) / tot
        abs_err += abs(score - gold_score)
        for g, m in zip(gm, marks):
            total += 1
            agree += g == m
            tp += g and m
            tn += (not g) and (not m)
            fp += m and not g
            fn += g and not m
    n = max(1, total)
    po = agree / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / max(1, n * n)
    return {"n_answers": len(items), "n_criteria": total, "criteria_accuracy": round(po, 3),
            "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None,
            "false_met": fp, "missed_met": fn, "score_mae": round(abs_err / max(1, len(items)), 2)}


# ------------------------------------------------------------------ прогон
EMPTY_RESUME = {f: None for f in RESUME_FIELDS} | {"skills": []}
EMPTY_NEED = {"specialization": None, "grades": [], "must_skills": [], "nice_skills": [], "work_formats": [],
              "city": None, "salary_from": None, "salary_to": None}


def run(data: dict, llm, raw_path: Path | None) -> dict:
    from app.services import llm as llm_mod
    from app.services import resume as resume_svc
    from app.services import rubric as rubric_svc
    from app.services.matching import service as matching

    llm_mod.set_llm(llm)
    use_llm = llm is not None
    texts = {i: pdf_roundtrip(r["text"]) for i, r in enumerate(data["resume"])}
    preds = {k: {} for k in ("resume", "need", "answer")}  # kind -> idx -> {method: pred}
    calls: list[dict] = []
    jobs = interleave(data)
    raw_f = raw_path.open("w", encoding="utf-8") if (raw_path and use_llm) else None
    started = time.perf_counter()
    interrupted = False
    fails_in_row = 0
    try:
        for k, (kind, i) in enumerate(jobs, 1):
            it = data[kind][i]
            lr = None
            if kind == "resume":
                rules = resume_svc.parse_rules(texts[i])
                raw = resume_svc.llm_extract(texts[i]) if use_llm else None
                preds[kind][i] = {"rules": rules, "llm": resume_svc.from_llm(raw) if raw else EMPTY_RESUME,
                                  "hybrid": resume_svc.merge(rules, raw)[0]}
            elif kind == "need":
                rules = matching.parse_need_rules(it["text"])
                raw = matching.need_llm_extract(it["text"]) if use_llm else None
                preds[kind][i] = {"rules": rules, "llm": matching.need_from_llm(raw) if raw else EMPTY_NEED,
                                  "hybrid": matching.merge_need(rules, raw)}
            else:
                rubric = it["task"]["rubric"]
                kw_score, kw_fb = rubric_svc.keyword_score(rubric, it["text"])
                kw = (kw_score, [c["met"] for c in kw_fb["criteria"]])
                raw = rubric_svc.llm_extract(it["task"]["body"], rubric, it["text"]) if use_llm else None
                lr = rubric_svc.from_llm(rubric, raw) if raw else None
                lp = (lr[0], [c["met"] for c in lr[1]["criteria"]]) if lr else (0.0, [False] * len(rubric))
                preds[kind][i] = {"rules": kw, "llm": lp, "hybrid": lp if lr else kw}
            if use_llm:
                rec = dict(llm.last)
                parsed = raw is not None and (kind != "answer" or lr is not None)
                rec.update(kind=kind, id=it["id"], parsed=parsed)
                calls.append(rec)
                if raw_f:
                    raw_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    raw_f.flush()
                fails_in_row = 0 if rec.get("ok") else fails_in_row + 1
                el = time.perf_counter() - started
                eta = el / k * (len(jobs) - k)
                status = "ok" if parsed else ("не JSON" if rec.get("ok") else rec.get("error", "ошибка")[:60])
                print(f"  [{k:>3}/{len(jobs)}] {kind:<6} {it['id']:<6} {rec['seconds']:6.1f} с  {status:<12} "
                      f"осталось ≈ {eta / 60:.0f} мин", flush=True)
                if fails_in_row >= 3:
                    print("Три запроса подряд завершились ошибкой — сервер недоступен или модель не загружается. "
                          "Останавливаю прогон.")
                    # сбой инфраструктуры, а не качества модели: эти тексты в метрики не идут
                    for kind_, i_ in jobs[k - fails_in_row:k]:
                        preds[kind_].pop(i_, None)
                    calls = calls[:-fails_in_row]
                    interrupted = True
                    break
    except KeyboardInterrupt:
        interrupted = True
        print("\nОстановлено. Считаю метрики по обработанным текстам.")
    finally:
        if raw_f:
            raw_f.close()
        llm_mod.set_llm(None)

    res: dict = {"partial": interrupted}
    for kind, evaluator, key in (("resume", eval_resumes, "resume"), ("need", eval_needs, "needs"),
                                 ("answer", eval_answers, "rubric")):
        idx = sorted(preds[kind])
        items = [data[kind][i] for i in idx]
        methods = ("rules", "llm", "hybrid") if use_llm else ("rules",)
        res[key] = {m: evaluator(items, [preds[kind][i][m] for i in idx]) for m in methods}
    if use_llm:
        res["timing"] = timing(calls)
        res["wall_minutes"] = round((time.perf_counter() - started) / 60, 1)
    return res


def timing(calls: list[dict]) -> dict:
    out = {}
    for kind in ("resume", "need", "answer"):
        cs = [c for c in calls if c["kind"] == kind]
        if not cs:
            continue
        secs = sorted(c["seconds"] for c in cs)
        toks = [(c.get("usage") or {}).get("completion_tokens") for c in cs if c.get("ok")]
        tps = []
        for c in cs:
            t = c.get("timings") or {}
            if t.get("predicted_per_second"):
                tps.append(t["predicted_per_second"])
            elif (c.get("usage") or {}).get("completion_tokens") and c["seconds"]:
                tps.append(c["usage"]["completion_tokens"] / c["seconds"])
        out[kind] = {"n": len(cs), "seconds_mean": round(sum(secs) / len(secs), 1),
                     "seconds_median": secs[len(secs) // 2], "seconds_max": secs[-1],
                     "invalid_share": round(sum(not c["parsed"] for c in cs) / len(cs), 3),
                     "errors": sum(not c.get("ok") for c in cs),
                     "completion_tokens_mean": round(sum(t for t in toks if t) / max(1, len([t for t in toks if t])), 0),
                     "tokens_per_second": round(sorted(tps)[len(tps) // 2], 1) if tps else None}
    return out


# ------------------------------------------------------------------ вывод
def pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def print_summary(res: dict, model: str | None) -> None:
    methods = ["rules", "llm", "hybrid"] if model else ["rules"]
    head = {"rules": "Правила", "llm": "LLM", "hybrid": "Гибрид"}
    w = 26

    def row(label, vals):
        print(f"  {label:<{w}}" + "".join(f"{v:>10}" for v in vals))

    r = res["resume"]
    print(f"\nРезюме (n = {r['rules']['n']})" + " " * (w - 12) + "".join(f"{head[m]:>10}" for m in methods))
    for f, label in RESUME_FIELDS.items():
        row(label, [pct(r[m]["fields"][f]) for m in methods])
    row("Навыки, F1", [f"{r[m]['skills']['f1']:.2f}" for m in methods])
    row("Все поля верно", [pct(r[m]["all_fields_ok"]) for m in methods])
    nd = res["needs"]
    print(f"\nПотребности (n = {nd['rules']['n']})")
    for k, label in (("specialization", "Специализация"), ("grades_exact", "Грейд"), ("salary", "Вилка"),
                     ("formats", "Формат работы"), ("city", "Город")):
        row(label, [pct(nd[m][k]) for m in methods])
    row("Навыки, F1", [f"{nd[m]['skills']['f1']:.2f}" for m in methods])
    row("Обязательные/желательные", [pct(nd[m]["must_nice_placement"]) for m in methods])
    rb = res["rubric"]
    print(f"\nАвтооценка ответов (n = {rb['rules']['n_answers']}; «Правила» = ключевые слова)")
    row("Критерии оценены верно", [pct(rb[m]["criteria_accuracy"]) for m in methods])
    row("Ошибка балла 0–10 (MAE)", [f"{rb[m]['score_mae']:.1f}" for m in methods])
    if model and res.get("timing"):
        print("\nВремя на один текст:")
        names = {"resume": "резюме", "need": "потребность", "answer": "ответ на задание"}
        for kind, t in res["timing"].items():
            print(f"  {names[kind]:<18} {t['seconds_mean']:5.1f} с в среднем (макс {t['seconds_max']:.0f} с), "
                  f"не разобрано ответов модели: {pct(t['invalid_share'])}"
                  + (f", генерация ≈ {t['tokens_per_second']:.0f} ток/с" if t.get("tokens_per_second") else ""))


def save(res: dict, model: str | None, base: str | None, args) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (model or "rules").lower()).strip("-")[:60] or "model"
    path = OUT / f"llm_compare_{slug}.json"
    meta = {"model": model, "base_url": base, "date": datetime.now().isoformat(timespec="seconds"),
            "quick": args.quick, "thinking_disabled": not args.allow_thinking,
            "machine": {"os": platform.platform(), "cpu": platform.processor() or platform.machine(),
                        "python": platform.python_version()}}
    path.write_text(json.dumps(meta | res, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main():
    args = parse_args()
    setup_env(args)
    data = load_data(args.quick)
    n = {k: len(v) for k, v in data.items()}
    print(f"Набор: {n['resume']} резюме, {n['need']} потребностей, {n['answer']} ответов на задания.")

    if args.rules_only:
        res = run(data, None, None)
        print_summary(res, None)
        print(f"\nРезультаты: {save(res, None, None, args)}")
        return

    conn = connect(args)
    if not conn:
        print("Сравнение с моделью не выполнено. Только правила: python validation/llm_compare.py --rules-only")
        return
    base, models = conn
    done: set[str] = set()
    while True:
        model = choose_model(models, args, done)
        if not model:
            break
        done.add(model)
        llm = make_llm(base, model, args.timeout)
        print(f"\nМодель: {model}  ({base})")
        print("Проверочный запрос (при первом обращении сервер может загружать модель — до пары минут)…")
        ok = llm.chat_json("Ты проверяешь связь.", 'Верни JSON {"ok": true}', {"ok": "boolean"})
        if not isinstance(ok, dict):
            print(f"Модель не ответила корректно: {llm.last.get('error') or (llm.last.get('raw') or '')[:200]}")
            if args.yes:
                break
            continue
        print(f"Связь есть ({llm.last['seconds']:.1f} с). Поехали: {sum(n.values())} текстов, тексты разных типов вперемешку.")
        slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")[:60]
        res = run(data, llm, OUT / f"llm_raw_{slug}.jsonl")
        print_summary(res, model)
        print(f"\nРезультаты: {save(res, model, base, args)}")
        if args.model or args.yes or len(models) == 1:
            break


if __name__ == "__main__":
    main()
