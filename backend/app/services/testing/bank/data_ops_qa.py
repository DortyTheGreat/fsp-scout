"""Data Science / ML, DevOps / SRE, QA."""
import ipaddress
import math
from collections import Counter

from .base import RU_NAMES, choice_item, input_item, multi_item, template

DS = ("data_science",)
OPS = ("devops",)
QA = ("qa",)


def _fmt(x: float, nd: int = 2) -> str:
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return s if s else "0"


# ============================================================ Data Science
@template("ds_pandas_groupby", "pandas: groupby и агрегаты", DS, {"pandas": 1.0, "python": 0.3}, "junior",
          a=1.1, b=-0.6, fmt="input", time_limit_s=150)
def _(rng):
    cities = rng.sample(["msk", "spb", "kzn", "ekb", "nsk"], 3)
    rows = [(rng.choice(cities), rng.randint(1, 9)) for _ in range(rng.randint(7, 9))]
    agg = rng.choice(["sum", "mean", "count", "max"])
    ask = rng.choice(["value", "idx"])
    groups = {}
    for c, q in rows:
        groups.setdefault(c, []).append(q)
    val = {c: {"sum": sum(v), "mean": sum(v) / len(v), "count": len(v), "max": max(v)}[agg] for c, v in groups.items()}
    best = max(val.values())
    winners = [c for c, v in val.items() if v == best]
    if ask == "idx" and len(winners) > 1:
        ask = "value"
    code = ("df = pd.DataFrame({\n    'city': " + str([r[0] for r in rows]) + ",\n    'qty':  " +
            str([r[1] for r in rows]) + "\n})\n" +
            (f"print(df.groupby('city')['qty'].{agg}().max())" if ask == "value"
             else f"print(df.groupby('city')['qty'].{agg}().idxmax())"))
    ans = _fmt(best) if ask == "value" else winners[0]
    return input_item("Что выведет код? (для дробей — до 2 знаков после точки)", ans, code=code, lang="python",
                      tol=0.01 if ask == "value" else None, placeholder="ответ")


@template("ds_classification_metrics", "Метрики классификации", DS, {"ml": 1.0, "statistics": 0.3}, "junior",
          a=1.2, b=-0.3, fmt="input", time_limit_s=150)
def _(rng):
    tp, fp, fn, tn = rng.randint(10, 90), rng.randint(5, 40), rng.randint(5, 40), rng.randint(50, 300)
    metric = rng.choice(["precision", "recall", "f1", "accuracy"])
    p, r = tp / (tp + fp), tp / (tp + fn)
    val = {"precision": p, "recall": r, "f1": 2 * p * r / (p + r), "accuracy": (tp + tn) / (tp + fp + fn + tn)}[metric]
    return input_item(f"Матрица ошибок бинарного классификатора: TP = {tp}, FP = {fp}, FN = {fn}, TN = {tn}. "
                      f"Чему равен {metric}? Округлите до двух знаков.", _fmt(round(val, 2)), tol=0.011,
                      placeholder="0.xx")


@template("ds_median", "Статистика: медиана и среднее", DS, {"statistics": 1.0}, "junior", a=0.9, b=-1.3,
          fmt="input", time_limit_s=90)
def _(rng):
    xs = [rng.randint(1, 50) for _ in range(rng.choice([6, 7, 8, 9]))]
    what = rng.choice(["median", "mean"])
    s = sorted(xs)
    n = len(s)
    val = (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2) if what == "median" else sum(xs) / n
    return input_item(f"Найдите {'медиану' if what == 'median' else 'среднее арифметическое'} выборки "
                      f"(до двух знаков): {xs}", _fmt(round(val, 2)), tol=0.011, placeholder="число")


@template("ds_bayes", "Теорема Байеса", DS, {"statistics": 1.0}, "middle", a=1.3, b=0.6, fmt="input",
          time_limit_s=200)
def _(rng):
    prev = rng.randint(1, 20)
    sens = rng.randint(80, 99)
    spec = rng.randint(85, 99)
    p = prev / 100 * sens / 100 / (prev / 100 * sens / 100 + (1 - prev / 100) * (1 - spec / 100))
    return input_item(f"Болезнь встречается у {prev}% людей. Тест выявляет больных с вероятностью {sens}% и даёт "
                      f"отрицательный результат у здоровых с вероятностью {spec}%. Тест положительный. Какова вероятность "
                      f"(в процентах, до целого), что человек болен?", round(p * 100), tol=1.0, placeholder="%")


@template("ds_gradient_step", "Градиентный спуск", DS, {"ml": 1.0}, "middle", a=1.1, b=0.3, fmt="input",
          time_limit_s=180)
def _(rng):
    k, m = rng.choice([0.5, 1, 1.5, 2, 2.5]), rng.randint(-10, 10)
    x0, lr = rng.randint(-20, 20), rng.choice([0.05, 0.1, 0.15, 0.2, 0.25, 0.3])
    steps = rng.choice([1, 2])
    x = x0
    for _ in range(steps):
        x = x - lr * 2 * k * (x - m)
    return input_item(f"Минимизируем f(x) = {k}·(x − ({m}))² градиентным спуском: x₀ = {x0}, шаг обучения {lr}. "
                      f"Чему равен x после {steps} {'шага' if steps == 1 else 'шагов'}? (до двух знаков)",
                      _fmt(round(x, 2)), tol=0.011, placeholder="число")


_FIT_CASES = [
    (0.99, 0.71, "Переобучение: модель запомнила обучающую выборку"),
    (0.62, 0.60, "Недообучение: модель слишком простая или признаки слабые"),
    (0.86, 0.84, "Модель обобщает нормально, большого разрыва нет"),
    (0.81, 0.97, "Подозрение на утечку или ошибку разбиения: валидация заметно лучше обучения"),
]


@template("ds_fit_diagnosis", "Диагностика обучения модели", DS, {"ml": 1.0}, "junior", a=1.0, b=-0.8,
          time_limit_s=90)
def _(rng):
    tr, va, ans = rng.choice(_FIT_CASES)
    tr = round(tr + rng.uniform(-0.01, 0.01), 2)
    va = round(va + rng.uniform(-0.01, 0.01), 2)
    return choice_item(rng, f"ROC-AUC на обучении = {tr}, на валидации = {va}. Какой вывод наиболее вероятен?",
                       ans, [c[2] for c in _FIT_CASES if c[2] != ans])


_LEAK = [
    ("Предсказываем отток клиента в следующем месяце.", "Флаг «клиент подал заявление на расторжение» за следующий месяц",
     ["Число обращений в поддержку за прошлые 3 месяца", "Тариф клиента", "Стаж клиента в днях"]),
    ("Предсказываем, вернёт ли заёмщик кредит.", "Число дней просрочки по этому кредиту на дату выгрузки",
     ["Доход на момент подачи заявки", "Число прошлых кредитов", "Регион"]),
    ("Предсказываем длительность госпитализации при поступлении.", "Дата выписки",
     ["Возраст пациента", "Диагноз при поступлении", "Отделение"]),
]


@template("ds_leakage", "Утечка целевой переменной", DS, {"ml": 1.0}, "middle", a=1.2, b=0.4, time_limit_s=120)
def _(rng):
    task, ans, wrong = rng.choice(_LEAK)
    return choice_item(rng, f"{task} Какой признак создаёт утечку целевой переменной?", ans, wrong)


_METRIC_CHOICE = [
    ("Мошеннические транзакции — 0.2% выборки; важно ранжировать операции для ручной проверки.",
     "PR-AUC (average precision)", ["Accuracy", "R²", "MSE"]),
    ("Прогноз спроса в штуках, крупные ошибки особенно дороги.", "RMSE", ["MAE", "Accuracy", "F1"]),
    ("Прогноз спроса, важно устойчивое к выбросам среднее отклонение в штуках.", "MAE", ["RMSE", "ROC-AUC", "Log-loss"]),
    ("Нужны откалиброванные вероятности для расчёта ожидаемых потерь.", "Log-loss", ["Accuracy", "F1", "ROC-AUC"]),
]


@template("ds_metric_choice", "Выбор метрики под задачу", DS, {"ml": 1.0}, "middle", a=1.1, b=0.1, time_limit_s=120)
def _(rng):
    q, a, w = rng.choice(_METRIC_CHOICE)
    return choice_item(rng, f"Какую метрику выбрать? {q}", a, w)


@template("ds_ab_test", "A/B-тест: значимость", DS, {"statistics": 1.0}, "senior", a=1.3, b=1.1, time_limit_s=240)
def _(rng):
    n = rng.randint(5, 200) * 100
    pa = rng.randint(30, 200) / 1000
    lift = rng.choice([-1, 1, 1, 1]) * rng.randint(1, 30) / 1000
    ca, cb = round(n * pa), round(n * (pa + lift))
    p1, p2 = ca / n, cb / n
    pp = (ca + cb) / (2 * n)
    z = (p2 - p1) / math.sqrt(pp * (1 - pp) * 2 / n)
    if abs(z) < 1.96:
        ans = "Различие не значимо на уровне 5%"
    elif z > 0:
        ans = "Значимо: B лучше A (p < 0.05)"
    else:
        ans = "Значимо: A лучше B (p < 0.05)"
    return choice_item(rng, f"A/B-тест, по {n} пользователей в группе. Конверсия: A — {ca} ({p1:.1%}), B — {cb} ({p2:.1%}). "
                       f"Двусторонний z-тест для долей, α = 0.05. Вывод?", ans,
                       ["Различие не значимо на уровне 5%", "Значимо: B лучше A (p < 0.05)", "Значимо: A лучше B (p < 0.05)",
                        "Вывод сделать нельзя без t-теста Стьюдента"])


@template("dl_conv_output", "CNN: размер выхода свёртки", DS, {"deep_learning": 1.0}, "middle", a=1.2, b=0.6,
          fmt="input", time_limit_s=150)
def _(rng):
    h = rng.randint(7, 128) * 4
    k = rng.choice([1, 3, 5, 7, 9, 11])
    s = rng.choice([1, 2, 2, 3, 4])
    p = rng.choice([0, 1, 2, k // 2])
    out = (h - k + 2 * p) // s + 1
    return input_item(f"Вход — изображение {h}×{h}. Свёрточный слой: ядро {k}×{k}, stride {s}, padding {p}. "
                      f"Какая высота выходной карты признаков?", out, placeholder="число")


@template("dl_params", "Нейросети: число параметров", DS, {"deep_learning": 1.0}, "senior", a=1.2, b=0.9,
          fmt="input", time_limit_s=180)
def _(rng):
    sizes = [rng.randint(2, 128) * 4] + [rng.randint(1, 64) * 4 for _ in range(rng.randint(1, 3))] + [rng.randint(1, 20)]
    total = sum((a + 1) * b for a, b in zip(sizes, sizes[1:]))
    code = "nn.Sequential(\n" + ",\n".join(
        f"    nn.Linear({a}, {b})" + (",\n    nn.ReLU()" if i < len(sizes) - 2 else "")
        for i, (a, b) in enumerate(zip(sizes, sizes[1:]))) + "\n)"
    return input_item("Сколько обучаемых параметров у модели (веса + смещения)?", total, code=code, lang="python",
                      placeholder="число")


@template("ds_broadcasting", "NumPy: broadcasting", DS, {"pandas": 1.0, "python": 0.3}, "middle", a=1.2, b=0.5,
          time_limit_s=120)
def _(rng):
    cases = [((3, 4), (4,), "(3, 4)"), ((3, 4), (3,), "Ошибка: формы несовместимы"), ((3, 1), (1, 5), "(3, 5)"),
             ((2, 3, 4), (3, 1), "(2, 3, 4)"), ((5, 1, 3), (4, 1), "(5, 4, 3)"), ((4,), (4, 1), "(4, 4)"),
             ((2, 3), (2, 1), "(2, 3)"), ((2, 3), (1, 2), "Ошибка: формы несовместимы")]
    sa, sb, ans = rng.choice(cases)
    opts = sorted({c[2] for c in cases} | {str(sa), str(sb)})
    return choice_item(rng, f"Какой формы будет результат a + b, если a.shape = {sa}, b.shape = {sb}?", ans,
                       [o for o in opts if o != ans])


@template("ds_kfold", "Кросс-валидация", DS, {"ml": 1.0}, "junior", a=1.0, b=-0.9, fmt="input", time_limit_s=90)
def _(rng):
    k = rng.choice([3, 4, 5, 6, 8, 10])
    n = k * rng.randint(20, 3000)
    return input_item(f"Датасет из {n} объектов, {k}-fold кросс-валидация без перемешивания групп. "
                      f"Сколько объектов в обучающей части на каждой итерации?", n - n // k, placeholder="число")


# ============================================================ DevOps / SRE
@template("ops_chmod", "Linux: права доступа", OPS + ("backend",), {"linux": 1.0}, "junior", a=1.0, b=-0.7,
          fmt="input", time_limit_s=120)
def _(rng):
    digits = [rng.randint(4, 7), rng.randint(0, 7), rng.randint(0, 7)]
    sym = "".join(("r" if d & 4 else "-") + ("w" if d & 2 else "-") + ("x" if d & 1 else "-") for d in digits)
    if rng.random() < 0.5:
        return input_item(f"Права файла в выводе ls -l: -{sym}. Какой восьмеричный аргумент chmod их задаёт?",
                          "".join(map(str, digits)), placeholder="например, 644")
    return input_item(f"Выполнили chmod {''.join(map(str, digits))} file. Как права выглядят в ls -l (9 символов после типа файла)?",
                      sym, placeholder="rwxr-xr-x")


@template("ops_cidr_hosts", "Сети: размер подсети", OPS + ("backend",), {"networking": 1.0}, "middle", a=1.1, b=0.0,
          fmt="input", time_limit_s=120)
def _(rng):
    pfx = rng.randint(20, 29)
    net = ipaddress.ip_network(f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.0/{pfx}", strict=False)
    return input_item(f"Сколько адресов можно назначить хостам в подсети {net}? (без адреса сети и широковещательного)",
                      net.num_addresses - 2, placeholder="число")


@template("ops_cidr_contains", "Сети: принадлежность адреса подсети", OPS, {"networking": 1.0}, "middle",
          a=1.2, b=0.5, time_limit_s=150)
def _(rng):
    pfx = rng.choice([22, 23, 25, 26, 27, 28])
    base = ipaddress.ip_address(f"192.168.{rng.randint(0, 255)}.{rng.randint(0, 255)}")
    net = ipaddress.ip_network(f"{base}/{pfx}", strict=False)
    inside = str(net[rng.randint(1, net.num_addresses - 2)])
    outside = set()
    while len(outside) < 3:
        cand = ipaddress.ip_address(int(net.network_address) + rng.choice([-1, -2, net.num_addresses, net.num_addresses + 1,
                                                                            net.num_addresses * 2, -net.num_addresses]))
        if cand not in net:
            outside.add(str(cand))
    return choice_item(rng, f"Какой адрес принадлежит подсети {net}?", inside, sorted(outside))


def _dockerfile(rng):
    """Случайный Dockerfile: Python или Node, «правильный» (зависимости отдельно) или «наивный» порядок."""
    if rng.random() < 0.5:
        base = rng.choice(["python:3.12-slim", "python:3.11-slim", "python:3.13-alpine"])
        deps, install = "requirements.txt", rng.choice(["RUN pip install -r requirements.txt",
                                                        "RUN pip install --no-cache-dir -r requirements.txt"])
        srcs = ["main.py", "app/api.py", "app/models.py", "tests/test_api.py"]
        cmd = 'CMD ["python", "main.py"]'
    else:
        base = rng.choice(["node:22-alpine", "node:20-slim"])
        deps, install = "package.json package-lock.json", "RUN npm ci"
        srcs = ["src/index.ts", "src/App.tsx", "public/logo.svg"]
        cmd = 'CMD ["npm", "start"]'
    lines = [f"FROM {base}"]
    if rng.random() < 0.5:
        lines.append(rng.choice(["RUN apt-get update && apt-get install -y curl", "RUN apk add --no-cache curl"]
                                if "alpine" not in base else ["RUN apk add --no-cache curl"]))
    lines.append("WORKDIR /app")
    if rng.random() < 0.4:
        lines.append(rng.choice(["ENV PYTHONUNBUFFERED=1", "ENV NODE_ENV=production", "ARG VERSION=1.0"]))
    naive = rng.random() < 0.3
    if naive:
        lines += ["COPY . .", install]
    else:
        lines += [f"COPY {deps} ./", install, "COPY . ."]
    if "node" in base and rng.random() < 0.7:
        lines.append("RUN npm run build")
    lines.append(cmd)
    changed = rng.choice(srcs + [deps.split()[0]])
    return lines, changed


@template("ops_docker_cache", "Docker: кэш слоёв", OPS + ("backend",), {"docker": 1.0}, "middle", a=1.3, b=0.3,
          fmt="input", time_limit_s=150)
def _(rng):
    df, changed = _dockerfile(rng)
    first = None
    for i, line in enumerate(df, 1):
        if line.startswith("COPY"):
            srcs = line.split()[1:-1]
            if "." in srcs or changed in srcs:  # COPY . . захватывает любой файл контекста
                first = i
                break
    code = "\n".join(f"{i:>2}  {l}" for i, l in enumerate(df, 1))
    return input_item(f"Образ уже собирался, кэш слоёв есть. Изменили только файл {changed}. С какой по номеру "
                      f"инструкции начнётся пересборка (первая инструкция, не взятая из кэша)?", first, code=code,
                      lang="dockerfile", placeholder="номер строки")


@template("ops_k8s_rolling", "Kubernetes: RollingUpdate", OPS, {"kubernetes": 1.0}, "senior", a=1.2, b=1.0,
          fmt="input", time_limit_s=180)
def _(rng):
    r = rng.randint(2, 40)
    surge = rng.choice([str(rng.randint(1, 5)), f"{rng.randint(1, 20) * 5}%"])
    unav = rng.choice(["0", str(rng.randint(1, 3)), f"{rng.randint(1, 10) * 5}%"])
    s_abs = math.ceil(r * int(surge[:-1]) / 100) if surge.endswith("%") else int(surge)
    u_abs = math.floor(r * int(unav[:-1]) / 100) if unav.endswith("%") else int(unav)
    ask = rng.choice(["max", "min"])
    ans = r + s_abs if ask == "max" else r - u_abs
    q = ("Какое максимальное число подов может существовать одновременно во время обновления?" if ask == "max"
         else "Какое минимальное число доступных (Ready) подов гарантируется во время обновления?")
    code = f"replicas: {r}\nstrategy:\n  type: RollingUpdate\n  rollingUpdate:\n    maxSurge: {surge}\n    maxUnavailable: {unav}"
    return input_item(q, ans, code=code, lang="yaml", placeholder="число")


@template("ops_sla_downtime", "SLA: допустимый простой", OPS + ("backend",), {"monitoring": 1.0}, "middle",
          a=1.1, b=0.0, fmt="input", time_limit_s=150)
def _(rng):
    sla = rng.choice(["99", "99.5", "99.8", "99.9", "99.95", "99.99", "99.7", "99.6", "99.85", "99.75", "99.25", "99.97"])
    days = rng.randint(7, 365)
    minutes = days * 24 * 60 * (1 - float(sla) / 100)
    return input_item(f"SLA доступности {sla}% за {days} дней. Сколько минут простоя допускается? (до одного знака)",
                      _fmt(round(minutes, 1), 1), tol=0.6, placeholder="минут")


@template("ops_error_budget", "SRE: бюджет ошибок", OPS, {"monitoring": 1.0}, "senior", a=1.2, b=0.9, fmt="input",
          time_limit_s=180)
def _(rng):
    slo = rng.choice([99.0, 99.5, 99.9, 99.8, 99.95])
    total = rng.randint(5, 200) * 100_000
    budget = total * (1 - slo / 100)
    errors = int(budget * rng.randint(5, 95) / 100)
    left = round(100 * (1 - errors / budget))
    return input_item(f"SLO: {slo}% успешных запросов за 28 дней. Прошло {total:,} запросов, из них {errors:,} — ошибки. "
                      f"Сколько процентов бюджета ошибок осталось? (до целого)".replace(",", " "), left, tol=1.0,
                      placeholder="%")


@template("ops_ci_critical_path", "CI/CD: длительность пайплайна", OPS, {"ci_cd": 1.0}, "middle", a=1.2, b=0.4,
          fmt="input", time_limit_s=200)
def _(rng):
    jobs = ["lint", "unit", "build", "integration", "e2e", "deploy"]
    dur = {j: rng.randint(1, 9) for j in jobs}
    deps = {"lint": [], "unit": [], "build": rng.choice([["lint"], [], ["unit"]]),
            "integration": ["build"], "e2e": rng.choice([["build"], ["build", "unit"]]),
            "deploy": ["integration", "e2e"] + rng.choice([[], ["lint"]])}
    fin = {}
    for j in jobs:
        fin[j] = dur[j] + max((fin[d] for d in deps[j]), default=0)
    code = "\n".join(f"{j:<12} {dur[j]} мин  needs: [{', '.join(deps[j])}]" for j in jobs)
    return input_item("Раннеров неограниченно, задачи стартуют сразу после завершения зависимостей. "
                      "За сколько минут завершится весь пайплайн?", max(fin.values()), code=code, lang="yaml",
                      placeholder="минут")


@template("ops_shell_pipeline", "Shell: конвейер команд", OPS + ("backend",), {"linux": 1.0}, "middle", a=1.2,
          b=0.3, fmt="input", time_limit_s=180)
def _(rng):
    ips = [f"10.0.0.{rng.randint(1, 6)}" for _ in range(rng.randint(8, 11))]
    codes = [rng.choice([200, 200, 200, 404, 500, 301]) for _ in ips]
    log = "\n".join(f"{ip} GET /api/{rng.choice(['a', 'b', 'c'])} {c}" for ip, c in zip(ips, codes))
    variant = rng.choice(["top_ip_count", "count_500", "uniq_ips"])
    if variant == "top_ip_count":
        cmd = "awk '{print $1}' access.log | sort | uniq -c | sort -nr | head -1 | awk '{print $1}'"
        ans = Counter(ips).most_common(1)[0][1]
    elif variant == "count_500":
        cmd = "awk '$4 >= 400' access.log | wc -l"
        ans = sum(1 for c in codes if c >= 400)
    else:
        cmd = "cut -d' ' -f1 access.log | sort -u | wc -l"
        ans = len(set(ips))
    return input_item("Что выведет команда для файла access.log?", ans, code=f"$ cat access.log\n{log}\n\n$ {cmd}",
                      lang="bash", placeholder="число")


@template("ops_bash_logic", "Shell: && и ||", OPS + ("qa",), {"linux": 1.0}, "junior", a=1.0, b=-0.4, fmt="input",
          time_limit_s=120)
def _(rng):
    parts = []
    for i in range(rng.randint(3, 4)):
        parts.append(rng.choice(["true", "false", f"echo {chr(65 + i)}"]))
    if not any(p.startswith("echo") for p in parts):
        parts[-1] = "echo Z"
    ops = [rng.choice(["&&", "||"]) for _ in range(len(parts) - 1)]
    # семантика bash: левоассоциативно, команда выполняется в зависимости от статуса предыдущей цепочки
    out, status = [], None
    for i, p in enumerate(parts):
        run = i == 0 or (ops[i - 1] == "&&" and status == 0) or (ops[i - 1] == "||" and status != 0)
        if run:
            if p == "true":
                status = 0
            elif p == "false":
                status = 1
            else:
                out.append(p.split()[1])
                status = 0
    cmd = parts[0] + "".join(f" {o} {p}" for o, p in zip(ops, parts[1:]))
    ans = " ".join(out) if out else "(ничего)"
    return input_item("Что будет выведено? Если несколько строк — через пробел; если ничего — напишите (ничего).",
                      ans, code=f"$ {cmd}", lang="bash", placeholder="вывод")


_OPS_CONCEPTS = [
    ("Под стартует 90 секунд (прогрев кэша); пока он не готов, трафик на него слать нельзя, но перезапускать не нужно.",
     "readinessProbe (и startupProbe для долгого старта)", ["livenessProbe с initialDelaySeconds: 0", "preStop hook",
                                                              "Увеличить replicas"]),
    ("Приложение иногда зависает в дедлоке и перестаёт отвечать, помогает только перезапуск.", "livenessProbe",
     ["readinessProbe", "PodDisruptionBudget", "HorizontalPodAutoscaler"]),
    ("Сайту нужен адрес www, указывающий на другое доменное имя CDN.", "CNAME", ["A", "MX", "TXT"]),
    ("Нужно подтвердить владение доменом для сервиса и прописать SPF.", "TXT", ["CNAME", "AAAA", "NS"]),
    ("В контейнере сервис слушает 127.0.0.1:8000, запуск docker run -p 8000:8000, но снаружи недоступен.",
     "Слушать 0.0.0.0 внутри контейнера", ["Открыть порт в EXPOSE — этого достаточно", "Добавить --network none",
                                            "Запустить контейнер с --privileged"]),
]


@template("ops_concepts", "Эксплуатация: типовые ситуации", OPS, {"kubernetes": 0.6, "networking": 0.6, "docker": 0.4},
          "middle", a=1.0, b=-0.2, time_limit_s=120)
def _(rng):
    q, a, w = rng.choice(_OPS_CONCEPTS)
    return choice_item(rng, q, a, w)


@template("ops_cron", "cron: расписание", OPS, {"linux": 1.0}, "junior", a=1.0, b=-0.5, time_limit_s=120)
def _(rng):
    m, h = rng.choice([0, 5, 15, 30, 45]), rng.randint(0, 23)
    dows = {"1-5": "по будням", "0": "по воскресеньям", "*": "каждый день", "6,0": "по выходным"}
    dow = rng.choice(list(dows))
    expr = f"{m} {h} * * {dow}"
    correct = f"В {h:02d}:{m:02d} {dows[dow]}"
    wrong = [f"В {m:02d}:{h:02d} {dows[dow]}" if m < 24 and m != h else f"Каждые {m or 60} минут в {h} час",
             f"В {h:02d}:{m:02d} {dows[rng.choice([d for d in dows if d != dow])]}",
             f"Каждую минуту с {h:02d}:00 до {h:02d}:59 {dows[dow]}",
             f"Каждые {h or 24} часов в {m} минут"]
    return choice_item(rng, f"Когда будет выполняться задача с расписанием `{expr}`?", correct, wrong)


# ============================================================ QA
@template("qa_boundary_values", "Тест-дизайн: граничные значения", QA, {"test_design": 1.0}, "junior", a=1.1,
          b=-0.8, time_limit_s=120)
def _(rng):
    lo = rng.randint(0, 500)
    hi = lo + rng.randint(5, 2000)
    correct = f"{lo - 1}, {lo}, {hi}, {hi + 1}"
    wrong = [f"{lo}, {(lo + hi) // 2}, {hi}", f"{lo + 1}, {hi - 1}", f"{lo - 1}, {hi + 1}", f"0, {lo}, {hi}, {hi * 10}"]
    return choice_item(rng, f"Поле принимает целые числа от {lo} до {hi} включительно. Какой набор соответствует "
                       f"двухточечному анализу граничных значений?", correct, wrong)


@template("qa_equivalence", "Тест-дизайн: классы эквивалентности", QA, {"test_design": 1.0}, "middle", a=1.1,
          b=-0.1, fmt="input", time_limit_s=150)
def _(rng):
    lo = rng.choice([1, 18, 100])
    tiers = rng.randint(2, 4)
    cuts = sorted(rng.sample(range(lo + 5, lo + 200), tiers - 1))
    hi = cuts[-1] + rng.randint(10, 100)
    bounds = [lo] + cuts + [hi]
    desc = "; ".join(f"{bounds[i] if i == 0 else bounds[i] + 1}–{bounds[i + 1] if i < tiers - 1 else hi} → тариф {i + 1}"
                     for i in range(tiers))
    return input_item(f"Поле «количество» принимает целые от {lo} до {hi}. Правила: {desc}. Сколько классов эквивалентности "
                      f"для целочисленного ввода, включая два невалидных (меньше минимума и больше максимума)?",
                      tiers + 2, placeholder="число")


@template("qa_pairwise", "Тест-дизайн: попарное тестирование", QA, {"test_design": 1.0}, "senior", a=1.2, b=1.0,
          fmt="input", time_limit_s=200)
def _(rng):
    params = [("ОС", ["Windows", "macOS", "Linux", "Android"]), ("Браузер", ["Chrome", "Firefox", "Safari", "Яндекс"]),
              ("Язык", ["ru", "en", "kk"]), ("Тариф", ["free", "pro"]), ("Роль", ["гость", "пользователь", "админ"])]
    chosen = rng.sample(params, 3)
    sizes = [rng.randint(2, len(v)) for _, v in chosen]
    s = sorted(sizes, reverse=True)
    desc = "; ".join(f"{n}: {', '.join(v[:k])}" for (n, v), k in zip(chosen, sizes))
    return input_item(f"Три независимых параметра — {desc}. Какое минимальное число тестов покроет все пары значений "
                      f"любых двух параметров (pairwise)?", s[0] * s[1], placeholder="число",
                      explanation="Нижняя граница — произведение двух наибольших размеров; для трёх параметров она достижима")


_SEVERITY = [
    ("При оплате заказа у всех пользователей падает 500, деньги не списываются.", "Blocker / критический"),
    ("Опечатка в тексте футера на странице «О компании».", "Trivial / незначительный"),
    ("Фильтр по дате в отчёте игнорирует последний день диапазона, есть обходной путь — выбрать день позже.",
     "Major / значительный"),
    ("Кнопка «Экспорт» на 2 px смещена относительно макета в Safari.", "Minor / незначительный визуальный"),
]


@template("qa_severity", "Оценка серьёзности дефекта", QA, {"test_design": 1.0}, "junior", a=0.9, b=-1.1,
          time_limit_s=90)
def _(rng):
    q, a = rng.choice(_SEVERITY)
    return choice_item(rng, f"Какую серьёзность (severity) присвоить дефекту? {q}", a, [x for _, x in _SEVERITY if x != a])


@template("qa_fixture_scope", "pytest: область видимости фикстур", QA, {"test_automation": 1.0, "python": 0.4},
          "middle", a=1.2, b=0.5, fmt="input", time_limit_s=150)
def _(rng):
    m1, m2 = rng.randint(1, 30), rng.randint(1, 30)
    scope = rng.choice(["function", "module", "session"])
    ans = {"function": m1 + m2, "module": 2, "session": 1}[scope]
    code = (f"# conftest.py\n@pytest.fixture(scope='{scope}')\ndef db():\n    print('setup')\n    yield connect()\n\n"
            f"# test_a.py: {m1} тест(ов), каждый принимает db\n# test_b.py: {m2} тест(ов), каждый принимает db")
    return input_item("Запускаем `pytest -s` для обоих файлов. Сколько раз будет напечатано setup?", ans, code=code,
                      lang="python", placeholder="число")


_AQA = [
    ("UI-тест иногда падает: кнопка ещё не кликабельна после загрузки страницы. Как исправить правильно?",
     "Явное ожидание условия (кликабельность элемента) вместо фиксированных пауз",
     ["time.sleep(5) перед кликом", "Перезапускать упавший тест до 3 раз и не разбираться", "Отключить тест"]),
    ("Как распределить автотесты по пирамиде тестирования?", "Больше всего модульных, меньше интеграционных, меньше всего UI/E2E",
     ["Больше всего UI-тестов: они ближе к пользователю", "Поровну на каждом уровне", "Только E2E, остальные избыточны"]),
    ("Тест API проверяет создание заказа и зависит от данных, оставленных предыдущим тестом. Чем это плохо и что делать?",
     "Тесты должны быть независимы: каждый готовит свои данные (фикстуры/фабрики)",
     ["Ничего страшного, если порядок запуска фиксирован", "Нужно объединить тесты в один большой",
      "Нужно запускать тесты только последовательно в одном потоке"]),
]


@template("qa_automation_concepts", "Автоматизация тестирования: практики", QA, {"test_automation": 1.0},
          "junior", a=1.0, b=-0.5, time_limit_s=120)
def _(rng):
    q, a, w = rng.choice(_AQA)
    return choice_item(rng, q, a, w)


@template("qa_negative_api", "API-тестирование: негативные проверки", QA, {"test_design": 0.6, "http_api": 0.8},
          "middle", a=1.1, b=0.2, fmt="multi", time_limit_s=150)
def _(rng):
    pos = ["POST /users с валидным email и паролем → 201", "GET /users/{id} существующего пользователя → 200",
           "PATCH /users/{id} владельцем профиля → 200"]
    neg = ["POST /users с уже занятым email → 409", "GET /users/{id} без токена → 401",
           "POST /users с паролем из 3 символов → 422", "DELETE /users/{id} чужого профиля → 403",
           "GET /users/abc (нечисловой id) → 404/422"]
    p = rng.sample(pos, rng.randint(1, 2))
    n = rng.sample(neg, 5 - len(p))
    return multi_item(rng, "Отметьте все негативные тест-кейсы.", n, p)
