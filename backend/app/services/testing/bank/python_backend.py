"""Python и бэкенд. Ответы вычисляются выполнением/моделированием сгенерированного кода."""
import contextlib
import io

from .base import IDENTS, RU_NAMES, choice_item, input_item, near_misses, template

PY = ("backend", "data_science", "qa", "devops")


def _run(code: str) -> str:
    """Выполняет СГЕНЕРИРОВАННЫЙ НАМИ фрагмент (не пользовательский ввод) и возвращает stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(code, {"__builtins__": __builtins__})  # noqa: S102 — код целиком из шаблона
    return buf.getvalue().strip()


@template("py_slicing", "Python: срезы", PY, {"python": 1.0}, "junior", a=1.1, b=-1.1, fmt="input", time_limit_s=90)
def _(rng):
    name = rng.choice(IDENTS)
    xs = rng.sample(range(1, 60), rng.randint(7, 10))
    i = rng.randint(-len(xs) + 1, 3)
    j = rng.choice([None, rng.randint(4, len(xs))])
    k = rng.choice([1, 2, 2, 3, -1])
    if k < 0:
        i, j = rng.randint(4, len(xs) - 1), rng.choice([None, 1])
    sl = f"{i}:{'' if j is None else j}:{k}" if k != 1 else f"{i}:{'' if j is None else j}"
    code = f"{name} = {xs}\nprint({name}[{sl}])"
    out = _run(code)
    return input_item("Что выведет код? Ответ — в том виде, как его печатает print.", out, code=code, lang="python",
                      placeholder="[...]")


@template("py_mutable_default", "Python: изменяемый аргумент по умолчанию", PY, {"python": 1.0},
          "middle", a=1.4, b=0.2, fmt="input", time_limit_s=120)
def _(rng):
    fn = rng.choice(["add", "collect", "track", "push"])
    calls = [rng.randint(1, 9) for _ in range(rng.randint(2, 4))]
    explicit = rng.randrange(len(calls))
    lines = [f"def {fn}(x, acc=[]):", "    acc.append(x)", "    return acc", ""]
    for i, c in enumerate(calls):
        lines.append(f"r{i} = {fn}({c}, [])" if i == explicit else f"r{i} = {fn}({c})")
    last = max(i for i in range(len(calls)) if i != explicit) if len(calls) > 1 else 0
    lines.append(f"print(len(r{last}))")
    code = "\n".join(lines)
    return input_item("Что выведет код?", _run(code), code=code, lang="python", placeholder="число")


@template("py_closure_late_binding", "Python: замыкания и позднее связывание", PY, {"python": 1.0},
          "senior", a=1.4, b=1.0, time_limit_s=150)
def _(rng):
    n = rng.randint(3, 6)
    k = rng.randint(2, 19)
    variant = rng.choice(["late", "default"])
    if variant == "late":
        code = f"fs = [lambda: i * {k} for i in range({n})]\nprint([f() for f in fs])"
    else:
        code = f"fs = [lambda i=i: i * {k} for i in range({n})]\nprint([f() for f in fs])"
    out = _run(code)
    alt1 = str([i * k for i in range(n)])
    alt2 = str([(n - 1) * k] * n)
    alt3 = str([0] * n)
    alt4 = str([(i + 1) * k for i in range(n)])
    return choice_item(rng, "Что выведет код?", out, [alt1, alt2, alt3, alt4], code=code, lang="python")


@template("py_generator_sum", "Python: генераторы", PY, {"python": 1.0}, "middle", a=1.1, b=0.0,
          fmt="input", time_limit_s=150)
def _(rng):
    conds = {"x % 2 == 0": lambda x: x % 2 == 0, "x % 3 != 0": lambda x: x % 3 != 0, "x > 5": lambda x: x > 5}
    while True:
        step, limit = rng.randint(2, 7), rng.randint(20, 90)
        cond = rng.choice(list(conds))
        produced = [x for x in range(0, limit, step) if conds[cond](x)]
        if len(produced) >= 4:
            break
    take = min(rng.randint(3, 7), len(produced) - 1)  # генератор не должен исчерпаться
    code = (f"def gen():\n    x = 0\n    while x < {limit}:\n        if {cond}:\n            yield x\n        x += {step}\n\n"
            f"g = gen()\nnext(g)\nprint(sum(next(g) for _ in range({take})))")
    return input_item("Что выведет код?", _run(code), code=code, lang="python", placeholder="число")


@template("py_finally_return", "Python: try/except/finally", PY, {"python": 1.0}, "middle", a=1.2, b=0.5,
          time_limit_s=120)
def _(rng):
    a, b = rng.randint(1, 99), rng.randint(100, 999)
    variant = rng.choice(["finally_return", "except_flow", "else_branch"])
    if variant == "finally_return":
        code = (f"def f():\n    try:\n        return {a}\n    finally:\n        return {b}\n\nprint(f())")
        wrong = [str(a), f"{a}\n{b}", "SyntaxError"]
    elif variant == "except_flow":
        code = (f"def f():\n    r = []\n    try:\n        r.append({a})\n        1 / 0\n        r.append({b})\n"
                f"    except ZeroDivisionError:\n        r.append(-1)\n    finally:\n        r.append(0)\n    return r\n\nprint(f())")
        wrong = [str([a, -1]), str([a, b, 0]), str([-1, 0])]
    else:
        code = (f"def f():\n    r = []\n    try:\n        r.append({a})\n    except Exception:\n        r.append(-1)\n"
                f"    else:\n        r.append({b})\n    finally:\n        r.append(0)\n    return r\n\nprint(f())")
        wrong = [str([a, 0]), str([a, -1, 0]), str([a, b])]
    return choice_item(rng, "Что выведет код?", _run(code), wrong, code=code, lang="python")


@template("py_sorted_key", "Python: сортировка с ключом", PY, {"python": 1.0}, "junior", a=1.0, b=-0.5,
          fmt="input", time_limit_s=120)
def _(rng):
    words = rng.sample(["кот", "дом", "лес", "арбуз", "море", "сад", "поле", "гора", "река", "ночь", "ветер"], 6)
    key = rng.choice(["(len(w), w)", "(-len(w), w)", "w[-1]"])
    idx = rng.randint(0, 3)
    code = f"words = {words}\nprint(sorted(words, key=lambda w: {key})[{idx}])"
    return input_item("Что выведет код?", _run(code), code=code, lang="python", placeholder="слово")


@template("py_set_dict", "Python: множества и словари", PY, {"python": 1.0}, "junior", a=1.0, b=-0.9,
          fmt="input", time_limit_s=90)
def _(rng):
    xs = [rng.randint(1, 8) for _ in range(rng.randint(7, 10))]
    ys = [rng.randint(4, 12) for _ in range(rng.randint(5, 8))]
    variant = rng.choice(["inter", "diff", "dictcomp", "sym"])
    if variant == "inter":
        code = f"a = {xs}\nb = {ys}\nprint(len(set(a) & set(b)))"
    elif variant == "diff":
        code = f"a = {xs}\nb = {ys}\nprint(len(set(a) - set(b)))"
    elif variant == "sym":
        code = f"a = {xs}\nb = {ys}\nprint(len(set(a) ^ set(b)))"
    else:
        code = f"a = {xs}\nd = {{x % 4: x for x in a}}\nprint(sum(d.values()))"
    return input_item("Что выведет код?", _run(code), code=code, lang="python", placeholder="число")


@template("py_class_attr", "Python: атрибуты класса и экземпляра", PY, {"python": 1.0}, "middle",
          a=1.3, b=0.6, fmt="input", time_limit_s=150)
def _(rng):
    cls = rng.choice(["Counter", "Box", "Node", "Bag", "Store", "Pool", "Cache", "Queue"])
    n1, n2 = rng.randint(1, 9), rng.randint(1, 9)
    variant = rng.choice(["list", "int"])
    if variant == "list":
        code = (f"class {cls}:\n    items = []\n    def add(self, x):\n        self.items.append(x)\n\n"
                f"a, b = {cls}(), {cls}()\n" + "".join(f"a.add({i})\n" for i in range(n1)) +
                "".join(f"b.add({i})\n" for i in range(n2)) + "print(len(a.items))")
    else:
        s0 = rng.randint(0, 9)
        code = (f"class {cls}:\n    n = {s0}\n    def inc(self):\n        self.n += 1\n\n"
                f"a, b = {cls}(), {cls}()\n" + "a.inc()\n" * n1 + "b.inc()\n" * n2 + f"print({cls}.n + a.n)")
    return input_item("Что выведет код?", _run(code), code=code, lang="python", placeholder="число")


@template("py_asyncio_timing", "asyncio: время выполнения", ("backend", "qa", "devops"), {"async": 1.0, "python": 0.4},
          "middle", a=1.3, b=0.4, fmt="input", time_limit_s=180)
def _(rng):
    d = [rng.randint(2, 18) / 2 for _ in range(3)]
    d = [int(x) if x == int(x) else x for x in d]
    variant = rng.choice(["gather", "sequential", "mixed", "blocking"])
    if variant == "gather":
        body = f"    await asyncio.gather(job({d[0]}), job({d[1]}), job({d[2]}))"
        ans = max(d)
    elif variant == "sequential":
        body = f"    await job({d[0]})\n    await job({d[1]})\n    await job({d[2]})"
        ans = sum(d)
    elif variant == "mixed":
        body = f"    await asyncio.gather(job({d[0]}), job({d[1]}))\n    await job({d[2]})"
        ans = max(d[0], d[1]) + d[2]
    else:
        # blocking стартует первым и держит цикл событий d1 секунд, затем обе job идут конкурентно
        body = f"    await asyncio.gather(blocking({d[1]}), job({d[0]}), job({d[2]}))"
        ans = d[1] + max(d[0], d[2])
    code = ("import asyncio, time\n\nasync def job(t):\n    await asyncio.sleep(t)\n\n"
            "async def blocking(t):\n    time.sleep(t)\n\nasync def main():\n" + body + "\n\nasyncio.run(main())")
    return input_item("Сколько примерно секунд будет выполняться программа? (накладными расходами пренебречь)",
                      ans, code=code, lang="python", placeholder="секунд", tol=0.01,
                      explanation="gather выполняет корутины конкурентно; time.sleep блокирует цикл событий")


_CPU_CASES = [
    ("Нужно параллельно посчитать хэши тысяч больших файлов, упирается в CPU (CPython).",
     "multiprocessing / ProcessPoolExecutor"),
    ("Сервис делает сотни параллельных HTTP-запросов к внешнему API и ждёт ответов.",
     "asyncio (или ThreadPoolExecutor) — задача ограничена вводом-выводом"),
    ("Тяжёлые матричные вычисления в numpy, которые и так отпускают GIL внутри C-кода.",
     "Потоки допустимы: numpy отпускает GIL на тяжёлых операциях"),
]


@template("py_gil_choice", "Конкурентность в CPython: выбор подхода", ("backend", "data_science", "devops"),
          {"async": 1.0, "python": 0.5}, "senior", a=1.1, b=1.2, time_limit_s=150)
def _(rng):
    case, ans = rng.choice(_CPU_CASES)
    return choice_item(rng, f"Какой подход к параллелизму уместнее? {case}", ans,
                       [a for _, a in _CPU_CASES if a != ans] + ["threading.Thread — потоки всегда ускоряют CPU-задачи",
                                                                 "Увеличить recursionlimit"])


# ============================================================ бэкенд-проектирование
@template("be_n_plus_one", "ORM: проблема N+1", ("backend",), {"web_frameworks": 1.0, "sql": 0.5},
          "middle", a=1.3, b=0.3, fmt="input", time_limit_s=150)
def _(rng):
    n = rng.randint(2, 500)
    variant = rng.choice(["naive", "naive", "select_related", "prefetch"])
    model = rng.choice([("Post", "author", "posts"), ("Order", "customer", "orders"), ("Ticket", "assignee", "tickets")])
    if variant == "naive":
        qs, ans = f"{model[0]}.objects.all()[:{n}]", n + 1
    elif variant == "select_related":
        qs, ans = f"{model[0]}.objects.select_related('{model[1]}')[:{n}]", 1
    else:
        qs, ans = f"{model[0]}.objects.prefetch_related('{model[1]}')[:{n}]", 2
    code = f"{model[2]} = {qs}\nfor obj in {model[2]}:\n    print(obj.{model[1]}.name)"
    return input_item(f"Django ORM. В таблице не меньше {n} записей, у каждой задан {model[1]} (ForeignKey). "
                      f"Сколько SQL-запросов выполнит фрагмент?", ans, code=code, lang="python", placeholder="число")


@template("be_littles_law", "Ёмкость системы: закон Литтла", ("backend", "devops"), {"system_design": 1.0},
          "middle", a=1.2, b=0.6, fmt="input", time_limit_s=150)
def _(rng):
    rps = rng.randint(15, 300) * 10
    ms = rng.randint(4, 60) * 5
    ans = rps * ms / 1000
    ans_s = str(int(ans)) if ans == int(ans) else str(ans)
    return input_item(f"Сервис получает в среднем {rps} запросов в секунду, каждый держит соединение с БД в среднем {ms} мс. "
                      f"Сколько соединений с БД заняты одновременно в среднем?", ans_s, tol=0.5, placeholder="число",
                      explanation="L = λ·W")


@template("be_token_bucket", "Rate limiting: token bucket", ("backend", "devops"), {"system_design": 1.0},
          "senior", a=1.2, b=1.1, fmt="input", time_limit_s=200)
def _(rng):
    cap = rng.randint(5, 40)
    rate = rng.randint(1, 9)
    burst1 = rng.randint(cap - 3, cap + 15)
    wait = rng.randint(1, 6)
    burst2 = rng.randint(3, 40)
    tokens = cap
    ok1 = min(burst1, tokens)
    tokens -= ok1
    tokens = min(cap, tokens + rate * wait)
    ok2 = min(burst2, tokens)
    return input_item(f"Лимитер «token bucket»: ёмкость {cap} токенов, пополнение {rate} токен(а) в секунду, "
                      f"в начале корзина полна. В момент t=0 одновременно пришло {burst1} запросов, а в момент t={wait} с — "
                      f"ещё {burst2}. Каждый запрос тратит 1 токен, без токена отклоняется. Сколько запросов будет "
                      f"принято всего?", ok1 + ok2, placeholder="число")


@template("be_cache_latency", "Кэширование: средняя задержка", ("backend", "devops"), {"caching_queues": 1.0},
          "middle", a=1.1, b=0.2, fmt="input", time_limit_s=150)
def _(rng):
    hit = rng.randint(50, 99)
    t_cache = rng.randint(1, 9)
    t_db = rng.randint(4, 60) * 5
    variant = rng.choice(["lookaside", "plain"])
    if variant == "lookaside":
        ans = hit / 100 * t_cache + (100 - hit) / 100 * (t_cache + t_db)
        txt = "при промахе сначала идёт обращение в кэш, затем в БД"
    else:
        ans = hit / 100 * t_cache + (100 - hit) / 100 * t_db
        txt = "время промаха — это только время запроса в БД"
    return input_item(f"Доля попаданий в кэш {hit}%, ответ из кэша — {t_cache} мс, из БД — {t_db} мс ({txt}). "
                      f"Какова средняя задержка чтения в мс?", round(ans, 2), tol=0.05, placeholder="мс")


_DESIGN_CASES = [
    ("Клиент повторяет POST /payments при таймауте; нельзя допустить двойного списания.",
     "Ключ идемпотентности от клиента + уникальный индекс и сохранение результата первой операции",
     ["Увеличить таймаут клиента", "Распределённая блокировка на весь сервис платежей",
      "Повторять запрос только по GET"]),
    ("Консьюмер очереди с гарантией at-least-once иногда получает сообщение дважды.",
     "Сделать обработку идемпотентной (дедупликация по id сообщения)",
     ["Перейти на exactly-once, отключив подтверждения", "Подтверждать сообщение до обработки",
      "Уменьшить число партиций до одной"]),
    ("После записи в БД нужно гарантированно опубликовать событие в брокер, без потери и без 2PC.",
     "Transactional outbox: запись события в таблицу в той же транзакции + отдельный ретранслятор",
     ["Сначала опубликовать событие, потом писать в БД", "Публиковать в finally-блоке",
      "Писать в БД и брокер параллельно в двух потоках"]),
    ("Чтение популярной карточки товара перегружает БД, данные меняются раз в несколько минут.",
     "Кэш с TTL и инвалидацией при изменении (cache-aside), защита от одновременного прогрева",
     ["Добавить индекс на все колонки", "Увеличить max_connections в 10 раз", "Шардировать таблицу по id"]),
]


@template("be_design_reliability", "Проектирование: надёжность и консистентность", ("backend",),
          {"system_design": 1.0, "caching_queues": 0.6}, "senior", a=1.2, b=1.0, time_limit_s=180)
def _(rng):
    case, ans, wrong = rng.choice(_DESIGN_CASES)
    return choice_item(rng, f"Какое решение правильное? {case}", ans, wrong)


@template("be_rest_design", "Проектирование REST API", ("backend", "frontend"), {"http_api": 1.0},
          "junior", a=1.0, b=-0.4, time_limit_s=120)
def _(rng):
    res = rng.choice([("orders", "заказ"), ("users", "пользователя"), ("projects", "проект"), ("invoices", "счёт")])
    action = rng.choice(["get_list", "create", "partial", "delete"])
    rid = rng.randint(10, 999)
    m = {"get_list": (f"Получить список {res[0]} второй страницы по 20 штук", f"GET /{res[0]}?page=2&size=20",
                      [f"POST /{res[0]}/list", f"GET /get{res[0].capitalize()}?p=2", f"GET /{res[0]}/2/20"]),
         "create": (f"Создать {res[1]}", f"POST /{res[0]}", [f"PUT /{res[0]}/create", f"GET /{res[0]}/new",
                                                              f"POST /{res[0]}/create/{rid}"]),
         "partial": (f"Изменить только одно поле у {res[1]} {rid}", f"PATCH /{res[0]}/{rid}",
                     [f"POST /{res[0]}/{rid}/update", f"GET /{res[0]}/{rid}?update=1", f"DELETE /{res[0]}/{rid}"]),
         "delete": (f"Удалить {res[1]} {rid}", f"DELETE /{res[0]}/{rid}",
                    [f"POST /{res[0]}/{rid}/delete", f"GET /{res[0]}/delete?id={rid}", f"PUT /{res[0]}/{rid}"])}
    q, ans, wrong = m[action]
    return choice_item(rng, f"Какой запрос лучше соответствует REST-стилю? Задача: {q}.", ans, wrong)
