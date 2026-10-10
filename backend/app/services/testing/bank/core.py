"""Общие шаблоны: алгоритмы, SQL, HTTP, Git, безопасность."""
import math
from collections import Counter, deque
import heapq

from .base import (ALL_SPECS, DEPTS, RU_NAMES, choice_item, input_item, multi_item, near_misses, template)

DEV = ("backend", "frontend", "data_science", "devops", "qa")


# ============================================================ алгоритмы
@template("alg_binsearch_steps", "Бинарный поиск: число сравнений", DEV, {"algorithms": 1.0},
          "junior", a=1.1, b=-0.7, fmt="input", time_limit_s=90)
def _(rng):
    n = rng.choice([rng.randint(100, 999), rng.randint(1000, 99_999), rng.randint(100_000, 5_000_000)])
    ans = math.ceil(math.log2(n + 1))
    return input_item(
        f"Отсортированный массив содержит {n:,} элементов (все различны). Какое **наибольшее** число "
        f"сравнений с искомым элементом может понадобиться бинарному поиску, чтобы найти элемент или "
        f"убедиться, что его нет?".replace(",", " "),
        ans, placeholder="число", explanation=f"⌈log2(n+1)⌉ = {ans}")


_COMPLEXITY_VARIANTS = [
    ("for i in range(n):\n    for j in range(i, n):\n        {op}", "O(n²)"),
    ("i = 1\nwhile i < n:\n    {op}\n    i *= 2", "O(log n)"),
    ("for i in range(n):\n    j = 1\n    while j < n:\n        {op}\n        j *= 2", "O(n log n)"),
    ("for i in range(n):\n    {op}\nfor j in range(n):\n    {op}", "O(n)"),
    ("for i in range(n):\n    for j in range(n):\n        for k in range(n):\n            {op}", "O(n³)"),
    ("for i in range(n):\n    for j in range({c}):\n        {op}", "O(n)"),
    ("i = n\nwhile i > 0:\n    for j in range(i):\n        {op}\n    i //= 2", "O(n)"),
    ("for i in range(1, n):\n    j = i\n    while j > 0:\n        {op}\n        j //= 2", "O(n log n)"),
]


@template("alg_complexity_5opt", "Оценка асимптотики фрагмента кода", DEV, {"algorithms": 1.0},
          "middle", a=1.3, b=0.1, time_limit_s=120)
def _(rng):
    code_t, ans = rng.choice(_COMPLEXITY_VARIANTS)
    op = rng.choice(["total += 1", "acc ^= i", "cnt += i % 3", "s += 2"])
    code = code_t.format(op=op, c=rng.choice([10, 64, 100, 1000]))
    opts = ["O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n³)"]
    return choice_item(rng, "Какова асимптотическая сложность фрагмента по времени от n?", ans,
                       [o for o in opts if o != ans], code=code, lang="python", n_options=5,
                       explanation="Подсчёт числа итераций вложенных циклов")


@template("alg_stack_ops", "Стек: последовательность операций", DEV, {"algorithms": 1.0},
          "junior", a=1.0, b=-1.2, fmt="input", time_limit_s=90)
def _(rng):
    st, ops = [], []
    for _ in range(rng.randint(7, 10)):
        if st and rng.random() < 0.4:
            st.pop()
            ops.append("pop()")
        else:
            v = rng.randint(1, 99)
            st.append(v)
            ops.append(f"push({v})")
    if not st:
        v = rng.randint(1, 99)
        st.append(v)
        ops.append(f"push({v})")
    return input_item("Над пустым стеком выполнили операции слева направо. Какой элемент окажется на вершине?",
                      st[-1], code=", ".join(ops), lang="text", placeholder="число")


@template("alg_queue_ops", "Очередь: последовательность операций", DEV, {"algorithms": 1.0},
          "junior", a=1.0, b=-1.0, fmt="input", time_limit_s=90)
def _(rng):
    q, ops = deque(), []
    for _ in range(rng.randint(7, 10)):
        if q and rng.random() < 0.4:
            q.popleft()
            ops.append("dequeue()")
        else:
            v = rng.randint(1, 99)
            q.append(v)
            ops.append(f"enqueue({v})")
    if not q:
        v = rng.randint(1, 99)
        q.append(v)
        ops.append(f"enqueue({v})")
    return input_item("Над пустой очередью (FIFO) выполнили операции слева направо. Какой элемент будет "
                      "извлечён следующим вызовом dequeue()?", q[0], code=", ".join(ops), lang="text",
                      placeholder="число")


def _random_graph(rng, n, m, weighted=False):
    nodes = [chr(ord("A") + i) for i in range(n)]
    edges = set()
    order = nodes[:]
    rng.shuffle(order)
    for i in range(1, n):  # связность
        u, v = order[i], rng.choice(order[:i])
        edges.add(tuple(sorted((u, v))))
    while len(edges) < m:
        u, v = rng.sample(nodes, 2)
        edges.add(tuple(sorted((u, v))))
    if weighted:
        return nodes, [(u, v, rng.randint(1, 9)) for u, v in sorted(edges)]
    return nodes, sorted(edges)


@template("alg_bfs_distance", "Кратчайший путь в невзвешенном графе", DEV, {"algorithms": 1.0},
          "middle", a=1.2, b=0.0, fmt="input", time_limit_s=150)
def _(rng):
    while True:
        nodes, edges = _random_graph(rng, rng.randint(7, 9), rng.randint(9, 12))
        adj = {x: [] for x in nodes}
        for u, v in edges:
            adj[u].append(v)
            adj[v].append(u)
        s, t = rng.sample(nodes, 2)
        dist = {s: 0}
        dq = deque([s])
        while dq:
            x = dq.popleft()
            for y in adj[x]:
                if y not in dist:
                    dist[y] = dist[x] + 1
                    dq.append(y)
        if dist[t] >= 2:
            break
    code = "\n".join(f"{u} — {v}" for u, v in edges)
    return input_item(f"Дан неориентированный граф (список рёбер). Сколько рёбер в кратчайшем пути от {s} до {t}?",
                      dist[t], code=code, lang="text", placeholder="число")


@template("alg_dijkstra", "Кратчайший путь во взвешенном графе", DEV, {"algorithms": 1.0},
          "senior", a=1.3, b=1.0, fmt="input", time_limit_s=240)
def _(rng):
    while True:
        nodes, edges = _random_graph(rng, rng.randint(6, 7), rng.randint(9, 11), weighted=True)
        adj = {x: [] for x in nodes}
        for u, v, w in edges:
            adj[u].append((v, w))
            adj[v].append((u, w))
        s, t = nodes[0], nodes[-1]
        dist = {s: 0}
        pq = [(0, s)]
        while pq:
            d, x = heapq.heappop(pq)
            if d > dist.get(x, 1e9):
                continue
            for y, w in adj[x]:
                if d + w < dist.get(y, 1e9):
                    dist[y] = d + w
                    heapq.heappush(pq, (d + w, y))
        direct = next((w for u, v, w in edges if {u, v} == {s, t}), None)
        if direct is None or direct > dist[t]:  # прямое ребро не должно быть ответом
            break
    code = "\n".join(f"{u} — {v}: {w}" for u, v, w in edges)
    return input_item(f"Дан неориентированный взвешенный граф (ребро: вес). Найдите длину кратчайшего пути от {s} до {t}.",
                      dist[t], code=code, lang="text", placeholder="число")


@template("alg_grid_paths", "Динамическое программирование: пути в сетке", DEV, {"algorithms": 1.0},
          "senior", a=1.2, b=0.9, fmt="input", time_limit_s=240)
def _(rng):
    r, c = rng.randint(3, 6), rng.randint(4, 6)
    blocked = set()
    while len(blocked) < rng.randint(1, 4):
        cell = (rng.randrange(r), rng.randrange(c))
        if cell not in {(0, 0), (r - 1, c - 1)}:
            blocked.add(cell)
    dp = [[0] * c for _ in range(r)]
    for i in range(r):
        for j in range(c):
            if (i, j) in blocked:
                continue
            if i == 0 and j == 0:
                dp[i][j] = 1
                continue
            dp[i][j] = (dp[i - 1][j] if i else 0) + (dp[i][j - 1] if j else 0)
    grid = "\n".join("".join("#" if (i, j) in blocked else "." for j in range(c)) for i in range(r))
    return input_item(f"Робот стоит в левом верхнем углу поля {r}×{c} и ходит только вправо или вниз. "
                      f"Клетки «#» заняты. Сколькими способами он может дойти до правого нижнего угла?",
                      dp[r - 1][c - 1], code=grid, lang="text", placeholder="число")


@template("alg_two_sum_pairs", "Подсчёт пар с заданной суммой", DEV, {"algorithms": 1.0},
          "middle", a=1.0, b=-0.2, fmt="input", time_limit_s=150)
def _(rng):
    xs = [rng.randint(1, 15) for _ in range(rng.randint(8, 10))]
    k = rng.randint(10, 20)
    cnt = sum(1 for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[i] + xs[j] == k)
    return input_item(f"Сколько пар индексов i < j таких, что a[i] + a[j] = {k}?", cnt,
                      code=f"a = {xs}", lang="python", placeholder="число")


_MASTER = [
    ("2·T(n/2) + O(n)", "O(n log n)"), ("2·T(n/2) + O(1)", "O(n)"), ("T(n/2) + O(1)", "O(log n)"),
    ("4·T(n/2) + O(n)", "O(n²)"), ("T(n/2) + O(n)", "O(n)"), ("3·T(n/3) + O(n)", "O(n log n)"),
    ("8·T(n/2) + O(n²)", "O(n³)"), ("4·T(n/2) + O(n²)", "O(n² log n)"),
]


@template("alg_master_theorem", "Рекуррентные соотношения", DEV, {"algorithms": 1.0},
          "senior", a=1.1, b=1.3, time_limit_s=150)
def _(rng):
    rec, ans = rng.choice(_MASTER)
    opts = ["O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n² log n)", "O(n³)"]
    return choice_item(rng, f"Время работы рекурсивного алгоритма задано соотношением T(n) = {rec}. "
                       f"Какова его асимптотика?", ans, [o for o in opts if o != ans])


# ============================================================ SQL
def _employees(rng, n):
    rows = []
    for i in range(n):
        rows.append((i + 1, rng.choice(RU_NAMES), rng.choice(DEPTS[:4]), rng.choice(range(60, 260, 10))))
    return rows


def _table(header, rows):
    w = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    line = lambda r: " | ".join(str(x).ljust(w[i]) for i, x in enumerate(r))
    return "\n".join([line(header), "-+-".join("-" * x for x in w)] + [line(r) for r in rows])


@template("sql_group_having", "SQL: GROUP BY и HAVING", ("backend", "data_science", "qa"), {"sql": 1.0},
          "junior", a=1.3, b=-0.3, fmt="input", time_limit_s=180)
def _(rng):
    rows = _employees(rng, rng.randint(8, 10))
    x = rng.choice([90, 100, 120, 150])
    k = rng.choice([2, 2, 3])
    cnt = Counter(r[2] for r in rows if r[3] > x)
    ans = sum(1 for d, c in cnt.items() if c >= k)
    q = (f"SELECT dept, COUNT(*)\nFROM employees\nWHERE salary > {x}\nGROUP BY dept\nHAVING COUNT(*) >= {k};")
    return input_item("Сколько строк вернёт запрос?\n\nТаблица employees:", ans,
                      code=_table(("id", "name", "dept", "salary"), rows) + "\n\n" + q, lang="sql",
                      placeholder="число строк")


@template("sql_left_join", "SQL: LEFT JOIN", ("backend", "data_science", "qa"), {"sql": 1.0},
          "middle", a=1.4, b=0.3, fmt="input", time_limit_s=180)
def _(rng):
    users = [(i + 1, rng.choice(RU_NAMES)) for i in range(rng.randint(4, 6))]
    orders = [(i + 101, rng.choice([u[0] for u in users] + [99]), rng.randint(1, 9) * 100)
              for i in range(rng.randint(5, 8))]
    cond = rng.choice(["", " AND o.amount > 300"])
    total = 0
    for uid, _ in users:
        m = [o for o in orders if o[1] == uid and (not cond or o[2] > 300)]
        total += max(1, len(m))
    q = f"SELECT u.id, o.id\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id{cond};"
    return input_item("Сколько строк вернёт запрос?", total,
                      code=_table(("users.id", "name"), users) + "\n\n" +
                      _table(("orders.id", "user_id", "amount"), orders) + "\n\n" + q,
                      lang="sql", placeholder="число строк",
                      explanation="LEFT JOIN сохраняет пользователей без заказов; условие в ON не фильтрует левую таблицу")


@template("sql_count_null", "SQL: COUNT и NULL", ("backend", "data_science", "qa"), {"sql": 1.0},
          "middle", a=1.2, b=0.6, fmt="input", time_limit_s=150)
def _(rng):
    vals = [rng.choice([None, None, rng.randint(1, 5)]) for _ in range(rng.randint(7, 10))]
    rows = [(i + 1, "NULL" if v is None else v) for i, v in enumerate(vals)]
    variant = rng.choice(["count_col", "count_distinct", "avg"])
    nn = [v for v in vals if v is not None]
    if not nn:
        vals[0] = 3
        rows[0] = (1, 3)
        nn = [3]
    if variant == "count_col":
        q, ans = "SELECT COUNT(*) - COUNT(bonus) FROM t;", len(vals) - len(nn)
    elif variant == "count_distinct":
        q, ans = "SELECT COUNT(DISTINCT bonus) FROM t;", len(set(nn))
    else:
        s = sum(nn)
        if s % len(nn):
            q, ans = "SELECT SUM(bonus) FROM t;", s
        else:
            q, ans = "SELECT AVG(bonus) FROM t;", s // len(nn)
    return input_item("Что вернёт запрос?", ans, code=_table(("id", "bonus"), rows) + "\n\n" + q, lang="sql",
                      placeholder="число")


@template("sql_window_rank", "SQL: оконные функции", ("backend", "data_science"), {"sql": 1.0, "postgresql": 0.5},
          "senior", a=1.3, b=1.1, fmt="input", time_limit_s=200)
def _(rng):
    rows = _employees(rng, rng.randint(7, 9))
    fn = rng.choice(["ROW_NUMBER", "RANK", "DENSE_RANK"])
    target = rng.choice(rows)
    same = sorted([r for r in rows if r[2] == target[2]], key=lambda r: (-r[3], r[0]))
    if fn == "ROW_NUMBER":
        ans = same.index(target) + 1
    elif fn == "RANK":
        ans = 1 + sum(1 for r in same if r[3] > target[3])
    else:
        ans = 1 + len({r[3] for r in same if r[3] > target[3]})
    q = (f"SELECT id, {fn}() OVER (PARTITION BY dept ORDER BY salary DESC, id) AS r\nFROM employees;"
         if fn == "ROW_NUMBER" else
         f"SELECT id, {fn}() OVER (PARTITION BY dept ORDER BY salary DESC) AS r\nFROM employees;")
    return input_item(f"Какое значение r получит строка с id = {target[0]}?", ans,
                      code=_table(("id", "name", "dept", "salary"), rows) + "\n\n" + q, lang="sql",
                      placeholder="число")


_INDEX_CASES = [
    ("SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT 20;",
     "CREATE INDEX ON orders (user_id, created_at DESC);",
     ["CREATE INDEX ON orders (created_at DESC, user_id);", "CREATE INDEX ON orders (created_at);",
      "Индекс не поможет: ORDER BY всегда требует полной сортировки"]),
    ("SELECT * FROM events WHERE status = 'new' AND created_at > now() - interval '1 day';",
     "CREATE INDEX ON events (status, created_at);",
     ["CREATE INDEX ON events (created_at, status);", "CREATE INDEX ON events USING hash (created_at);",
      "Два отдельных индекса на каждую колонку всегда эффективнее"]),
    ("SELECT * FROM users WHERE lower(email) = lower($1);",
     "CREATE INDEX ON users (lower(email));",
     ["CREATE INDEX ON users (email);", "CREATE INDEX ON users USING hash (email);",
      "Индекс не может использоваться, если в условии есть функция"]),
    ("SELECT * FROM docs WHERE tenant_id = $1 AND deleted_at IS NULL;  -- удалённых 95%",
     "CREATE INDEX ON docs (tenant_id) WHERE deleted_at IS NULL;",
     ["CREATE INDEX ON docs (deleted_at);", "CREATE INDEX ON docs (deleted_at, tenant_id);",
      "Индекс по NULL-значениям в PostgreSQL невозможен"]),
]


@template("sql_index_choice", "PostgreSQL: выбор индекса", ("backend",), {"postgresql": 1.0, "sql": 0.5},
          "senior", a=1.2, b=1.2, time_limit_s=150)
def _(rng):
    q, ans, wrong = rng.choice(_INDEX_CASES)
    return choice_item(rng, "Какой индекс лучше всего ускорит запрос?", ans, wrong, code=q, lang="sql")


_ISOLATION = [
    ("Транзакция дважды читает одну строку и видит разные значения, потому что между чтениями другая "
     "транзакция зафиксировала изменение. Какой минимальный уровень изоляции PostgreSQL это исключает?",
     "REPEATABLE READ"),
    ("Две транзакции читают остаток на двух счетах, каждая проверяет инвариант «сумма ≥ 0» и списывает "
     "со своего счёта; обе фиксируются, и инвариант нарушен (write skew). Какой уровень изоляции PostgreSQL это исключает?",
     "SERIALIZABLE"),
    ("Какой уровень изоляции используется в PostgreSQL по умолчанию?", "READ COMMITTED"),
]


@template("sql_isolation", "Транзакции и уровни изоляции", ("backend",), {"postgresql": 1.0, "system_design": 0.4},
          "senior", a=1.1, b=1.3, time_limit_s=150)
def _(rng):
    q, ans = rng.choice(_ISOLATION)
    return choice_item(rng, q, ans, [x for x in ["READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ",
                                                 "SERIALIZABLE"] if x != ans])


# ============================================================ HTTP
_HTTP_CASES = [
    ("Клиент успешно создал ресурс через POST, сервер вернул его адрес в Location.", "201 Created"),
    ("DELETE прошёл успешно, телу ответа нечего возвращать.", "204 No Content"),
    ("Запрос без токена к защищённому ресурсу.", "401 Unauthorized"),
    ("Пользователь аутентифицирован, но не имеет прав на ресурс.", "403 Forbidden"),
    ("Клиент превысил лимит запросов.", "429 Too Many Requests"),
    ("Попытка зарегистрировать email, который уже занят (конфликт состояния).", "409 Conflict"),
    ("Ресурс по указанному идентификатору не существует.", "404 Not Found"),
    ("Сервис временно на обслуживании, клиенту стоит повторить позже.", "503 Service Unavailable"),
    ("Клиент прислал If-None-Match, и ресурс не изменился.", "304 Not Modified"),
]
_HTTP_ALL = sorted({c for _, c in _HTTP_CASES} | {"400 Bad Request", "500 Internal Server Error", "200 OK"})


@template("http_status_code", "HTTP: коды ответов", ("backend", "frontend", "qa", "devops"), {"http_api": 1.0},
          "junior", a=1.0, b=-1.1, time_limit_s=90)
def _(rng):
    case, ans = rng.choice(_HTTP_CASES)
    return choice_item(rng, f"Какой код ответа наиболее уместен? {case}", ans, [c for c in _HTTP_ALL if c != ans])


@template("http_idempotency", "HTTP: идемпотентность методов", ("backend", "frontend", "qa"), {"http_api": 1.0},
          "middle", a=1.2, b=0.2, fmt="multi", time_limit_s=120)
def _(rng):
    methods = {"GET": True, "PUT": True, "DELETE": True, "HEAD": True, "OPTIONS": True, "POST": False, "PATCH": False}
    shown = rng.sample(list(methods), 5)
    if all(methods[m] for m in shown):
        shown[0] = "POST"
    if not any(methods[m] for m in shown):
        shown[0] = "PUT"
    correct = [m for m in shown if methods[m]]
    wrong = [m for m in shown if not methods[m]]
    return multi_item(rng, "Отметьте все методы, которые по спецификации HTTP являются идемпотентными.", correct, wrong)


@template("http_cors_preflight", "CORS: когда будет preflight", ("backend", "frontend"), {"http_api": 0.6, "browser": 0.8},
          "senior", a=1.1, b=0.9, time_limit_s=150)
def _(rng):
    cases = [
        ("fetch('https://api.other.ru/x', {method: 'POST', headers: {'Content-Type': 'application/json'}, body})", True),
        ("fetch('https://api.other.ru/x')", False),
        ("fetch('https://api.other.ru/x', {headers: {'X-Request-Id': id}})", True),
        ("fetch('https://api.other.ru/x', {method: 'POST', body: new FormData(form)})", False),
        ("fetch('https://api.other.ru/x', {method: 'DELETE'})", True),
        ("fetch('/api/x', {method: 'PUT', body})  // тот же origin", False),
    ]
    code, pre = rng.choice(cases)
    ans = "Да, браузер сначала отправит OPTIONS (preflight)" if pre else "Нет, preflight не нужен"
    return choice_item(rng, "Страница открыта на https://app.example.ru. Отправит ли браузер preflight-запрос?",
                       ans, ["Да, браузер сначала отправит OPTIONS (preflight)", "Нет, preflight не нужен",
                             "Запрос будет заблокирован без отправки", "Preflight зависит только от метода GET/POST"],
                       code=code, lang="javascript")


# ============================================================ Git
_GIT_CASES = [
    ("Отменить последний коммит, оставив изменения в индексе (staged).", "git reset --soft HEAD~1"),
    ("Отменить уже опубликованный в общую ветку коммит {h}, не переписывая историю.", "git revert {h}"),
    ("Перенести один коммит {h} из другой ветки в текущую.", "git cherry-pick {h}"),
    ("Временно убрать незакоммиченные изменения, чтобы переключиться на ветку {b}.", "git stash"),
    ("Изменить сообщение последнего (ещё не отправленного) коммита.", "git commit --amend"),
    ("Посмотреть, какой коммит последним изменил строку в файле {f}.", "git blame {f}"),
    ("Найти коммит, внёсший регрессию, двоичным поиском по истории.", "git bisect start"),
]


@template("git_command", "Git: выбор команды", ("backend", "frontend", "data_science", "devops", "qa"), {"git": 1.0},
          "junior", a=1.0, b=-0.6, time_limit_s=90)
def _(rng):
    h = "".join(rng.choice("0123456789abcdef") for _ in range(7))
    b = rng.choice(["hotfix/login", "feature/search", "release/2.4", "bugfix/cart"])
    f = rng.choice(["app/models.py", "src/App.tsx", "Dockerfile", "README.md"])
    case, ans = rng.choice(_GIT_CASES)
    fmt = lambda s: s.format(h=h, b=b, f=f)
    others = [fmt(a) for _, a in _GIT_CASES if a != ans] + ["git reset --hard HEAD~1", f"git rebase {b}"]
    return choice_item(rng, fmt(case), fmt(ans), others)


@template("git_merge_base", "Git: что попадёт в merge", ("backend", "frontend", "devops", "qa", "data_science"),
          {"git": 1.0}, "middle", a=1.0, b=0.3, fmt="input", time_limit_s=150)
def _(rng):
    k1, k2 = rng.randint(1, 25), rng.randint(1, 25)
    base = rng.randint(3, 60)
    return input_item(
        f"В ветке main {base} коммитов. От её последнего коммита создали ветку feature и сделали в ней {k1} коммитов. "
        f"Тем временем в main добавили ещё {k2}. Выполнили `git checkout main && git merge feature` (без squash и fast-forward невозможен). "
        f"Сколько коммитов станет в истории main (`git log --oneline main | wc -l`)?",
        base + k1 + k2 + 1, placeholder="число",
        explanation="Все коммиты обеих веток + merge-коммит")


# ============================================================ безопасность
_SQLI = [
    ('cur.execute(f"SELECT * FROM users WHERE login = \'{login}\'")', "Уязвим к SQL-инъекции"),
    ('cur.execute("SELECT * FROM users WHERE login = %s", (login,))', "Безопасен: параметризованный запрос"),
    ('cur.execute("SELECT * FROM users WHERE login = \'" + login.replace("\'", "") + "\'")', "Уязвим к SQL-инъекции"),
    ('User.objects.filter(login=login)', "Безопасен: параметризованный запрос"),
    ('cur.execute("SELECT * FROM users ORDER BY " + request.args["sort"])', "Уязвим к SQL-инъекции"),
]


@template("sec_sql_injection", "Безопасность: SQL-инъекции", ("backend", "qa"), {"security": 1.0, "sql": 0.3},
          "junior", a=1.1, b=-0.5, time_limit_s=90)
def _(rng):
    code, ans = rng.choice(_SQLI)
    return choice_item(rng, "Оцените фрагмент кода (login и параметры пришли от пользователя).", ans,
                       ["Уязвим к SQL-инъекции", "Безопасен: параметризованный запрос",
                        "Безопасен, если база PostgreSQL", "Уязвим только к XSS"], code=code, lang="python")


@template("sec_password_storage", "Безопасность: хранение паролей", ("backend", "qa", "devops"), {"security": 1.0},
          "middle", a=1.0, b=0.0, time_limit_s=90)
def _(rng):
    return choice_item(rng, "Как правильно хранить пароли пользователей в базе данных?",
                       rng.choice(["Хэш медленной функцией с солью (Argon2id, bcrypt, scrypt)",
                                   "Argon2id или bcrypt с уникальной солью для каждого пароля"]),
                       ["SHA-256 от пароля", "Шифрование AES с ключом в конфиге", "MD5 с общей солью",
                        "В открытом виде, но в отдельной таблице с ограниченным доступом"])
