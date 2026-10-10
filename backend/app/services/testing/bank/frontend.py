"""Фронтенд: JavaScript, браузер, CSS, React, TypeScript. Ответы вычисляются моделями семантики."""
from collections import deque

from .base import choice_item, input_item, multi_item, template

FE = ("frontend",)
FE_FULL = ("frontend", "backend")


# ------------------------------------------------------------ event loop: модель микро/макрозадач
def _simulate_event_loop(ops):
    out, micro, macro = [], deque(), []
    for seq, op in enumerate(ops):
        kind = op[0]
        if kind == "sync":
            out.append(op[1])
        elif kind == "micro":
            micro.append((op[1], 0))
        elif kind == "macro":
            macro.append((op[1], seq, op[2], op[3]))

    def drain():
        while micro:
            chain, i = micro.popleft()
            out.append(chain[i])
            if i + 1 < len(chain):
                micro.append((chain, i + 1))

    drain()
    for delay, _, label, inner in sorted(macro):
        out.append(label)
        if inner:
            micro.append(([inner], 0))
        drain()
    return out


def _js_for(op):
    kind = op[0]
    if kind == "sync":
        return f"console.log('{op[1]}');"
    if kind == "micro":
        s = "Promise.resolve()" + "".join(f".then(() => console.log('{x}'))" for x in op[1])
        return s + ";"
    delay, label, inner = op[1], op[2], op[3]
    if inner:
        return (f"setTimeout(() => {{\n  console.log('{label}');\n  Promise.resolve().then(() => console.log('{inner}'));\n}}, {delay});")
    return f"setTimeout(() => console.log('{label}'), {delay});"


@template("js_event_loop", "JavaScript: порядок выполнения (event loop)", FE_FULL, {"browser": 1.0, "javascript": 0.7},
          "middle", a=1.5, b=0.4, time_limit_s=180)
def _(rng):
    words = ["ping", "load", "init", "tick", "save", "draw", "send", "read", "done", "sync", "boot", "flush", "poll",
             "emit", "push", "pull", "fetch", "parse", "start", "stop", "open", "close", "next", "wait"]
    letters = iter(rng.sample(words, 10))
    ops = []
    kinds = ["sync", "micro", "macro", "sync", rng.choice(["micro2", "macro_inner", "macro10"])]
    rng.shuffle(kinds)
    for k in kinds:
        if k == "sync":
            ops.append(("sync", next(letters)))
        elif k == "micro":
            ops.append(("micro", [next(letters)]))
        elif k == "micro2":
            ops.append(("micro", [next(letters), next(letters)]))
        elif k == "macro":
            ops.append(("macro", 0, next(letters), None))
        elif k == "macro10":
            ops.append(("macro", 10, next(letters), None))
        else:
            ops.append(("macro", 0, next(letters), next(letters)))
    if not any(o[0] == "sync" for o in ops):
        ops.insert(0, ("sync", "Z"))
    correct = _simulate_event_loop(ops)
    program_order = []
    for o in ops:
        program_order += [o[1]] if o[0] == "sync" else (o[1] if o[0] == "micro" else [o[2]] + ([o[3]] if o[3] else []))
    syncs = [x for x in correct if any(o[0] == "sync" and o[1] == x for o in ops)]
    rest = [x for x in correct if x not in syncs]
    wrong = [" ".join(program_order), " ".join(rest + syncs), " ".join(syncs + rest[::-1]),
             " ".join(correct[1:] + correct[:1])]
    code = "\n".join(_js_for(o) for o in ops)
    return choice_item(rng, "В каком порядке будут выведены строки?", " ".join(correct), wrong, code=code,
                       lang="javascript", explanation="Синхронный код → микрозадачи (Promise) → макрозадачи (setTimeout)")


_EQ = [("0 == ''", True), ("0 === ''", False), ("null == undefined", True), ("null === undefined", False),
       ("'1' == 1", True), ("NaN == NaN", False), ("[] == false", True), ("[1] == 1", True), ("null == 0", False),
       ("undefined == 0", False), ("'' == false", True), ("'0' == false", True), ("[] == []", False),
       ("typeof null === 'object'", True), ("typeof NaN === 'number'", True), ("'b' + 'a' + +'a' === 'baNaN'", True),
       ("0.1 + 0.2 === 0.3", False), ("[] + [] === ''", True)]


@template("js_equality", "JavaScript: сравнения и приведение типов", FE, {"javascript": 1.0},
          "junior", a=1.1, b=-0.3, fmt="multi", time_limit_s=150)
def _(rng):
    while True:
        picked = rng.sample(_EQ, 5)
        if 1 <= sum(v for _, v in picked) <= 4:
            break
    return multi_item(rng, "Отметьте все выражения, которые вычисляются в true.",
                      [e for e, v in picked if v], [e for e, v in picked if not v])


@template("js_array_chain", "JavaScript: filter/map/reduce", FE, {"javascript": 1.0}, "junior", a=1.0, b=-1.0,
          fmt="input", time_limit_s=120)
def _(rng):
    arr = [rng.randint(1, 12) for _ in range(rng.randint(5, 8))]
    k, m, s = rng.randint(2, 3), rng.randint(2, 4), rng.choice([0, 0, 1, 10])
    res = sum(x * m for x in arr if x % k == 0) + s
    code = f"const a = {arr};\nconsole.log(a.filter(x => x % {k} === 0).map(x => x * {m}).reduce((acc, x) => acc + x, {s}));"
    return input_item("Что выведет код?", res, code=code, lang="javascript", placeholder="число")


@template("js_var_let_closure", "JavaScript: var/let в циклах и замыкания", FE, {"javascript": 1.0},
          "middle", a=1.3, b=0.1, time_limit_s=120)
def _(rng):
    n = rng.randint(2, 4)
    kw = rng.choice(["var", "let"])
    code = f"for ({kw} i = 0; i < {n}; i++) {{\n  setTimeout(() => console.log(i), 0);\n}}"
    seq = " ".join(str(i) for i in range(n))
    same = " ".join([str(n)] * n)
    ans = same if kw == "var" else seq
    wrong = [seq if kw == "var" else same, " ".join([str(n - 1)] * n), " ".join(["undefined"] * n),
             " ".join(str(i) for i in range(1, n + 1))]
    return choice_item(rng, "Что выведет код (через пробел)?", ans, wrong, code=code, lang="javascript")


@template("js_this_binding", "JavaScript: this, call, bind", FE, {"javascript": 1.0}, "senior", a=1.3, b=1.0,
          time_limit_s=150)
def _(rng):
    n1, n2, n3, n4 = rng.sample(["Ann", "Bob", "Kim", "Lee", "Max", "Zoe"], 4)
    base = (f"'use strict';\nconst obj = {{\n  name: '{n1}',\n  regular() {{ return this?.name; }},\n"
            f"  arrow: () => this?.name,\n}};\n")
    variants = [
        (f"console.log(obj.regular());", n1),
        (f"const f = obj.regular;\nconsole.log(f());", "undefined"),
        (f"console.log(obj.regular.call({{ name: '{n2}' }}));", n2),
        (f"const g = obj.regular.bind({{ name: '{n3}' }});\nconsole.log(g.call({{ name: '{n4}' }}));", n3),
        (f"console.log(obj.arrow.call({{ name: '{n2}' }}));", "undefined"),
    ]
    tail, ans = rng.choice(variants)
    opts = [n1, n2, n3, n4, "undefined", "TypeError"]
    return choice_item(rng, "Что выведет код (ES-модуль, строгий режим)?", ans, [o for o in opts if o != ans],
                       code=base + tail, lang="javascript")


_PROMISE_FNS = ["all", "allSettled", "race", "any"]


@template("js_promise_combinators", "JavaScript: Promise.all/race/any", FE_FULL, {"javascript": 1.0, "async": 0.4},
          "middle", a=1.2, b=0.6, time_limit_s=180)
def _(rng):
    ps = []
    for _ in range(3):
        ps.append((rng.choice([10, 20, 30, 40, 50]), rng.random() < 0.35, rng.randint(1, 9)))
    # уникальные времена — чтобы порядок был однозначен
    times = rng.sample([10, 20, 30, 40, 50], 3)
    ps = [(t, rej, v) for t, (_, rej, v) in zip(times, ps)]
    fn = rng.choice(_PROMISE_FNS)
    lines = ["const p = (ms, ok, v) => new Promise((res, rej) => setTimeout(() => ok ? res(v) : rej(v), ms));"]
    args = ", ".join(f"p({t}, {'false' if rej else 'true'}, {v})" for t, rej, v in ps)
    by_time = sorted(ps)
    if fn == "all":
        rejected = [x for x in by_time if x[1]]
        ans = f"err {rejected[0][2]}" if rejected else "ok " + ",".join(str(v) for _, _, v in ps)
        code_tail = f"Promise.all([{args}])\n  .then(v => console.log('ok', v.join(',')))\n  .catch(e => console.log('err', e));"
    elif fn == "allSettled":
        ok = sum(1 for x in ps if not x[1])
        ans = f"ok {ok}"
        code_tail = (f"Promise.allSettled([{args}])\n  .then(r => console.log('ok', r.filter(x => x.status === 'fulfilled').length))"
                     f"\n  .catch(e => console.log('err', e));")
    elif fn == "race":
        first = by_time[0]
        ans = f"err {first[2]}" if first[1] else f"ok {first[2]}"
        code_tail = f"Promise.race([{args}])\n  .then(v => console.log('ok', v))\n  .catch(e => console.log('err', e));"
    else:
        ful = [x for x in by_time if not x[1]]
        ans = f"ok {ful[0][2]}" if ful else "err AggregateError"
        code_tail = (f"Promise.any([{args}])\n  .then(v => console.log('ok', v))\n"
                     f"  .catch(e => console.log('err', e.constructor.name));")
    vals = [str(v) for _, _, v in ps]
    wrong = [f"ok {vals[0]}", f"err {vals[0]}", f"ok {vals[-1]}", f"err {vals[-1]}", "ok " + ",".join(vals),
             f"ok {len(vals)}", "err AggregateError", f"ok {sum(1 for x in ps if x[1])}"]
    return choice_item(rng, "Что выведет код?", ans, [w for w in wrong if w != ans],
                       code="\n".join(lines) + "\n" + code_tail, lang="javascript")


@template("fe_debounce_throttle", "Debounce и throttle", FE, {"javascript": 1.0, "browser": 0.5},
          "senior", a=1.2, b=1.1, fmt="input", time_limit_s=180)
def _(rng):
    t = sorted(rng.sample(range(0, 3000, 10), rng.randint(6, 12)))
    d = rng.choice([100, 150, 200, 250, 300, 400, 500])
    kind = rng.choice(["debounce", "throttle"])
    if kind == "debounce":
        calls = 1 + sum(1 for a, b in zip(t, t[1:]) if b - a >= d)
        desc = f"debounce с задержкой {d} мс (обработчик вызывается через {d} мс после последнего события серии)"
    else:
        calls, last = 0, None
        for x in t:
            if last is None or x - last >= d:
                calls += 1
                last = x
        desc = f"throttle с интервалом {d} мс (leading: вызов на первом событии, затем не чаще раза в {d} мс, хвостовой вызов не делается)"
    return input_item(f"Обработчик ввода обёрнут в {desc}. События пришли в моменты (мс): {', '.join(map(str, t))}. "
                      f"Сколько раз будет вызван обработчик?", calls, placeholder="число")


# ------------------------------------------------------------ CSS
_SELECTORS = [("p", (0, 0, 1)), (".note", (0, 1, 0)), ("#msg", (1, 0, 0)), ("p.note", (0, 1, 1)),
              (".note.warn", (0, 2, 0)), ("div p", (0, 0, 2)), (".wrap .warn", (0, 2, 0)),
              ("div > p.warn", (0, 1, 2)), ("#msg.note", (1, 1, 0)), ("*", (0, 0, 0)), ("p:first-child", (0, 1, 1))]
_COLORS = ["red", "green", "blue", "orange", "purple", "teal"]


@template("css_specificity", "CSS: специфичность селекторов", FE, {"html_css": 1.0}, "middle", a=1.3, b=0.2,
          time_limit_s=150)
def _(rng):
    rules = rng.sample(_SELECTORS, 4)
    colors = rng.sample(_COLORS, 4)
    important = rng.random() < 0.3
    imp_idx = min(range(4), key=lambda i: rules[i][1]) if important else -1
    best, best_key = None, None
    lines = []
    for i, ((sel, spec), col) in enumerate(zip(rules, colors)):
        imp = i == imp_idx
        key = (imp, spec, i)
        if best_key is None or key > best_key:
            best_key, best = key, col
        lines.append(f"{sel} {{ color: {col}{' !important' if imp else ''}; }}")
    html = '<div class="wrap">\n  <p id="msg" class="note warn">Текст</p>\n</div>'
    return choice_item(rng, "Каким цветом будет «Текст»? (p — первый ребёнок div)", best,
                       [c for c in colors if c != best], code=html + "\n\n<style>\n" + "\n".join(lines) + "\n</style>",
                       lang="html")


@template("css_box_model", "CSS: блочная модель", FE, {"html_css": 1.0}, "junior", a=1.1, b=-0.7, fmt="input",
          time_limit_s=120)
def _(rng):
    w, p, bd, m = rng.randint(10, 60) * 10, rng.randint(0, 40), rng.randint(0, 8), rng.randint(0, 40)
    sizing = rng.choice(["content-box", "border-box"])
    ask = rng.choice(["border", "outer"])
    border_box = w if sizing == "border-box" else w + 2 * p + 2 * bd
    ans = border_box if ask == "border" else border_box + 2 * m
    q = ("Какова ширина элемента по внешней границе рамки (border-box), в px?" if ask == "border"
         else "Сколько горизонтального места займёт элемент вместе с внешними отступами (margin), в px?")
    css = f".card {{\n  box-sizing: {sizing};\n  width: {w}px;\n  padding: {p}px;\n  border: {bd}px solid #ccc;\n  margin: {m}px;\n}}"
    return input_item(q, ans, code=css, lang="css", placeholder="px")


# ------------------------------------------------------------ React
@template("react_state_batching", "React: обновления состояния и батчинг", FE, {"react": 1.0},
          "middle", a=1.4, b=0.5, fmt="input", time_limit_s=180)
def _(rng):
    s = rng.randint(0, 20)
    upd = []
    for _ in range(rng.randint(2, 5)):
        upd.append((rng.choice(["value", "fn"]), rng.randint(1, 9)))
    if all(u[0] == "fn" for u in upd):
        upd[0] = ("value", upd[0][1])
    v = s
    lines = []
    for kind, k in upd:
        if kind == "value":
            v = s + k
            lines.append(f"    setCount(count + {k});")
        else:
            v = v + k
            lines.append(f"    setCount(c => c + {k});")
    code = (f"function Counter() {{\n  const [count, setCount] = useState({s});\n  const onClick = () => {{\n"
            + "\n".join(lines) + "\n  };\n  return <button onClick={onClick}>{count}</button>;\n}")
    return input_item("React 18. Какое число отобразится на кнопке после одного клика?", v, code=code, lang="jsx",
                      placeholder="число")


@template("react_effect_runs", "React: когда выполняется useEffect", FE, {"react": 1.0}, "middle", a=1.2, b=0.3,
          fmt="input", time_limit_s=150)
def _(rng):
    k = rng.randint(3, 40)       # всего повторных рендеров
    m = rng.randint(1, k - 1)    # из них id менялся
    variant = rng.choice(["empty", "none", "dep"])
    deps = {"empty": "[]", "none": "", "dep": "[id]"}[variant]
    ans = {"empty": 1, "none": 1 + k, "dep": 1 + m}[variant]
    code = f"useEffect(() => {{\n  load(id);\n}}{', ' + deps if deps else ''});"
    return input_item(f"Компонент смонтировался и затем перерисовался ещё {k} раз; при {m} из этих перерисовок изменился prop id. "
                      f"Сколько раз всего выполнится эффект? (production-сборка, без StrictMode)", ans,
                      code=code, lang="jsx", placeholder="число")


_REACT_CONCEPTS = [
    ("Список рендерится с key={index}; элементы можно удалять из начала списка, у каждого есть поле ввода. Что произойдёт?",
     "Состояние полей «съедет» на соседние элементы — key должен быть стабильным id",
     ["Ничего: index — рекомендуемый key", "React выбросит ошибку о дублирующихся ключах",
      "Список перестанет обновляться"]),
    ("Где правильно выполнять запрос данных при изменении параметра userId в функциональном компоненте?",
     "В useEffect с зависимостью [userId] (или через библиотеку запросов)",
     ["Прямо в теле компонента при каждом рендере", "В useMemo без зависимостей", "В обработчике onLoad у div"]),
    ("Дочерний компонент обёрнут в React.memo, но перерисовывается при каждом рендере родителя. Родитель передаёт onSave={() => save(id)}. В чём причина?",
     "Новая функция на каждый рендер — нужно useCallback",
     ["React.memo работает только с классами", "Нужно добавить key", "memo сравнивает props глубоко, и это дорого"]),
]


@template("react_concepts", "React: типичные ошибки", FE, {"react": 1.0}, "junior", a=1.0, b=-0.4, time_limit_s=120)
def _(rng):
    q, a, w = rng.choice(_REACT_CONCEPTS)
    return choice_item(rng, q, a, w)


_TS_CASES = [
    ("function f(x: string | number | null) {\n  if (typeof x === 'string') return;\n  if (x) {\n    x; // тип здесь?\n  }\n}",
     "number", ["string | number", "number | null", "never"]),
    ("type Shape = { kind: 'c'; r: number } | { kind: 's'; a: number };\nfunction area(s: Shape) {\n  if (s.kind === 'c') return;\n  s; // тип здесь?\n}",
     "{ kind: 's'; a: number }", ["Shape", "{ kind: 'c'; r: number }", "never"]),
    ("const xs = [1, 'a', true];\n// тип xs?", "(string | number | boolean)[]",
     ["[number, string, boolean]", "any[]", "unknown[]"]),
    ("const cfg = { mode: 'dark' } as const;\n// тип cfg.mode?", "\"dark\"", ["string", "any", "\"dark\" | \"light\""]),
    ("function g<T extends { id: number }>(x: T): T['id'] { return x.id; }\nconst r = g({ id: 1, n: 'a' });\n// тип r?",
     "number", ["1", "T", "{ id: number }"]),
]


@template("ts_narrowing", "TypeScript: вывод и сужение типов", FE, {"typescript": 1.0}, "middle", a=1.2, b=0.5,
          time_limit_s=150)
def _(rng):
    code, a, w = rng.choice(_TS_CASES)
    return choice_item(rng, "Какой тип выведет TypeScript в отмеченном месте?", a, w, code=code, lang="typescript")


_STORAGE = [
    ("Где хранить токен сессии, чтобы он был недоступен JavaScript на странице (защита от кражи через XSS)?",
     "Cookie с флагами HttpOnly, Secure, SameSite", ["localStorage", "sessionStorage", "Глобальная переменная window.token"]),
    ("Данные должны жить только пока открыта вкладка и не делиться между вкладками.",
     "sessionStorage", ["localStorage", "Cookie без срока действия", "IndexedDB"]),
    ("Нужно хранить в браузере сотни мегабайт структурированных данных офлайн-приложения.",
     "IndexedDB", ["localStorage", "Cookie", "sessionStorage"]),
]


@template("browser_storage", "Браузер: хранилища и безопасность", FE, {"browser": 1.0, "security": 0.4},
          "junior", a=1.0, b=-0.6, time_limit_s=90)
def _(rng):
    q, a, w = rng.choice(_STORAGE)
    return choice_item(rng, q, a, w)
