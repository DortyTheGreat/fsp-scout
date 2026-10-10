"""Каркас параметрических шаблонов заданий.

Шаблон = функция-генератор gen(rng) → экземпляр задания. Каждый показ — новый экземпляр
(случайный seed): другие числа, данные, имена, порядок вариантов. Правильный ответ вычисляется
генератором, а не хранится в банке — поэтому слитый «ответ на вопрос №7» бесполезен:
у следующего кандидата вопрос №7 другой, хотя проверяет то же умение и с той же трудностью
(экземпляры одного шаблона изоморфны — одинаковая структура решения).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable

ALL_SPECS = ("backend", "frontend", "data_science", "devops", "qa")


@dataclass
class Instance:
    prompt: str
    fmt: str = "single"                 # single | multi | input
    code: str | None = None
    lang: str | None = None
    options: list[str] | None = None
    answer: Any = None                  # single: индекс; multi: список индексов; input: список допустимых строк
    numeric_tol: float | None = None    # для input: допуск по числу
    placeholder: str | None = None
    explanation: str = ""               # показывается только в режиме разбора/админке, не во время теста

    def public(self) -> dict:
        """То, что уходит на клиент: без ключа ответа."""
        return {"prompt": self.prompt, "fmt": self.fmt, "code": self.code, "lang": self.lang,
                "options": self.options, "placeholder": self.placeholder}

    def fingerprint(self) -> str:
        """Отпечаток смысла экземпляра: текст, код и правильный ответ. Совпадает у «одинаковых» вопросов."""
        import hashlib
        ans = self.answer
        if self.options and isinstance(ans, int):
            ans = self.options[ans]
        elif self.options and isinstance(ans, list) and ans and isinstance(ans[0], int):
            ans = sorted(self.options[i] for i in ans)
        return hashlib.sha1(repr((self.prompt, self.code, ans)).encode()).hexdigest()

    def key(self) -> dict:
        return {"answer": self.answer, "numeric_tol": self.numeric_tol, "explanation": self.explanation}


@dataclass
class Template:
    id: str
    title: str
    specs: tuple[str, ...]
    skills: dict[str, float]
    level: str
    a: float
    b: float
    fmt: str
    time_limit_s: int
    gen: Callable[[random.Random], Instance] = field(repr=False)

    def render(self, seed: int) -> Instance:
        rng = random.Random(seed)
        inst = self.gen(rng)
        inst.fmt = inst.fmt or self.fmt
        return inst

    def variant_space(self, n: int = 200) -> int:
        """Сколько различных (по тексту, коду и ответу) экземпляров дают n случайных seed."""
        if getattr(self, "_vs", None) is None:
            seen = set()
            for seed in range(n):
                i = self.render(seed)
                correct = (i.options[i.answer] if i.fmt == "single" else
                           tuple(sorted(i.options[k] for k in i.answer)) if i.fmt == "multi" else tuple(i.answer))
                seen.add((i.prompt, i.code, correct))
            self._vs = len(seen)
        return self._vs

    @property
    def c(self) -> float:
        """Вероятность угадывания: 1/число вариантов для single, ~0 для ввода ответа."""
        if self.fmt == "single":
            return 0.2 if self.id.endswith("_5opt") else 0.25
        if self.fmt == "multi":
            return 0.05
        return 0.0


TEMPLATES: dict[str, Template] = {}


def template(id: str, title: str, specs, skills: dict[str, float], level: str, a: float, b: float,
             fmt: str = "single", time_limit_s: int = 120):
    def deco(fn: Callable[[random.Random], Instance]):
        if id in TEMPLATES:
            raise ValueError(f"duplicate template id {id}")
        TEMPLATES[id] = Template(id=id, title=title, specs=tuple(specs), skills=skills, level=level,
                                 a=a, b=b, fmt=fmt, time_limit_s=time_limit_s, gen=fn)
        return fn
    return deco


# ------------------------------------------------------------------ помощники генераторов
def choice_item(rng: random.Random, prompt: str, correct: str, distractors: list[str], *,
                code: str | None = None, lang: str | None = None, n_options: int = 4,
                explanation: str = "") -> Instance:
    """Задание с выбором одного ответа: перемешивает варианты, убирает дубли."""
    seen = {correct}
    pool = []
    for d in distractors:
        if d not in seen:
            seen.add(d)
            pool.append(d)
    rng.shuffle(pool)
    opts = [correct] + pool[: n_options - 1]
    rng.shuffle(opts)
    return Instance(prompt=prompt, fmt="single", code=code, lang=lang, options=opts,
                    answer=opts.index(correct), explanation=explanation)


def multi_item(rng: random.Random, prompt: str, correct: list[str], wrong: list[str], *,
               code: str | None = None, lang: str | None = None, explanation: str = "") -> Instance:
    opts = list(dict.fromkeys(correct + wrong))
    rng.shuffle(opts)
    return Instance(prompt=prompt, fmt="multi", code=code, lang=lang, options=opts,
                    answer=sorted(opts.index(c) for c in correct), explanation=explanation)


def input_item(prompt: str, answers, *, code: str | None = None, lang: str | None = None,
               tol: float | None = None, placeholder: str | None = None, explanation: str = "") -> Instance:
    if not isinstance(answers, (list, tuple)):
        answers = [answers]
    return Instance(prompt=prompt, fmt="input", code=code, lang=lang, answer=[str(x) for x in answers],
                    numeric_tol=tol, placeholder=placeholder, explanation=explanation)


def near_misses(value: int, rng: random.Random, k: int = 6, spread: int = 3) -> list[str]:
    """Правдоподобные неверные числовые варианты рядом с правильным."""
    out = set()
    tries = 0
    while len(out) < k and tries < 100:
        tries += 1
        d = rng.choice([-spread, -2, -1, 1, 2, spread, value // 2 if value > 4 else 4])
        v = value + d
        if v != value and v >= 0:
            out.add(str(v))
    return list(out)


_NUM_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def normalize(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", "", s)
    s = s.replace('"', "'")
    if _NUM_RE.match(s):
        s = s.replace(",", ".")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
    return s


def check_answer(key: dict, response: Any) -> bool:
    ans = key["answer"]
    if isinstance(ans, int):  # single
        try:
            return int(response) == ans
        except (TypeError, ValueError):
            return False
    if isinstance(ans, list) and ans and isinstance(ans[0], int) or (isinstance(ans, list) and not ans):
        try:
            return sorted(int(x) for x in (response or [])) == sorted(ans)
        except (TypeError, ValueError):
            return False
    # input
    resp = normalize(str(response if response is not None else ""))
    tol = key.get("numeric_tol")
    for a in ans:
        if normalize(a) == resp:
            return True
        if tol is not None:
            try:
                if abs(float(normalize(a)) - float(resp)) <= tol:
                    return True
            except ValueError:
                pass
    return False


RU_NAMES = ["Анна", "Борис", "Вера", "Глеб", "Дарья", "Егор", "Жанна", "Захар", "Ирина", "Кирилл",
            "Лидия", "Максим", "Нина", "Олег", "Полина", "Роман", "Софья", "Тимур", "Ульяна", "Фёдор"]
DEPTS = ["sales", "dev", "ops", "hr", "qa", "data"]
IDENTS = ["items", "data", "values", "nums", "xs", "arr", "buf", "row"]
