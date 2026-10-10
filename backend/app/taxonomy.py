"""Справочник платформы: направления → специализации, грейды, навыки, отрасли, причины отказа.

Категория кандидата = (специализация, грейд). Справочник составлен по общепринятым в ИТ понятиям;
на этапе MVP — основные направления. Добавление специализации = запись здесь + шаблоны заданий
в app/services/testing/bank/.
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------- грейды
# Порог θ (шкала способности IRT) — нижняя граница грейда. Тест на грейд G проверяет θ ≥ cut(G).
GRADES: list[dict] = [
    {"slug": "intern", "name": "Стажёр", "experience": "без коммерческого опыта", "cut": -99.0, "order": 0},
    {"slug": "junior", "name": "Junior", "experience": "до 1–2 лет", "cut": -1.0, "order": 1},
    {"slug": "middle", "name": "Middle", "experience": "2–4 года", "cut": 0.0, "order": 2},
    {"slug": "senior", "name": "Senior", "experience": "4+ лет", "cut": 1.0, "order": 3},
]
GRADE_BY_SLUG = {g["slug"]: g for g in GRADES}
GRADE_ORDER = [g["slug"] for g in GRADES]
TESTABLE_GRADES = ["junior", "middle", "senior"]  # стажёр — без теста-порога (любой результат)


def grade_cut(slug: str) -> float:
    return GRADE_BY_SLUG[slug]["cut"]


def grade_from_theta(theta: float) -> str:
    result = "intern"
    for g in GRADES:
        if theta >= g["cut"]:
            result = g["slug"]
    return result


def grade_shift(slug: str, delta: int) -> str | None:
    i = GRADE_ORDER.index(slug) + delta
    return GRADE_ORDER[i] if 0 <= i < len(GRADE_ORDER) else None


# ---------------------------------------------------------------- навыки
@dataclass(frozen=True)
class Skill:
    slug: str
    name: str
    group: str
    synonyms: tuple[str, ...] = field(default_factory=tuple)


_S = Skill
SKILLS: list[Skill] = [
    # языки
    _S("python", "Python", "Языки", ("python", "питон", "пайтон", "py3", "python3")),
    _S("java", "Java", "Языки", ("java", "джава", "spring", "spring boot")),
    _S("go", "Go", "Языки", ("golang", " go ", "go,", "go/", "гоу")),
    _S("javascript", "JavaScript", "Языки", ("javascript", "js", "es6", "ecmascript")),
    _S("typescript", "TypeScript", "Языки", ("typescript", "ts")),
    _S("cpp", "C++", "Языки", ("c++", "cpp", "плюсы", "stl")),
    _S("csharp", "C#", "Языки", ("c#", "csharp", ".net", "dotnet", "asp.net")),
    # бэкенд
    _S("sql", "SQL", "Данные", ("sql", "join", "select", "оконн")),
    _S("postgresql", "PostgreSQL", "Данные", ("postgres", "postgresql", "постгрес", "psql")),
    _S("http_api", "HTTP и REST API", "Бэкенд", ("rest", "http", "api", "restful", "openapi", "swagger", "grpc")),
    _S("web_frameworks", "Веб-фреймворки (Django/FastAPI/Flask)", "Бэкенд",
       ("django", "fastapi", "flask", "aiohttp", "express", "nestjs", "spring")),
    _S("async", "Асинхронность и конкурентность", "Бэкенд",
       ("asyncio", "async", "конкурентн", "многопоточ", "threading", "goroutine", "горутин")),
    _S("system_design", "Проектирование систем", "Бэкенд",
       ("system design", "архитектур", "микросервис", "highload", "хайлоад", "масштабир")),
    _S("caching_queues", "Кэши и очереди", "Бэкенд", ("redis", "kafka", "rabbitmq", "очеред", "кэш", "celery")),
    # фронтенд
    _S("html_css", "HTML и CSS", "Фронтенд", ("html", "css", "вёрстк", "верстк", "scss", "flexbox", "grid")),
    _S("react", "React", "Фронтенд", ("react", "реакт", "redux", "next.js", "nextjs", "hooks")),
    _S("browser", "Браузер и Web API", "Фронтенд", ("dom", "event loop", "web api", "браузер", "fetch")),
    # общее
    _S("algorithms", "Алгоритмы и структуры данных", "Основы",
       ("алгоритм", "структуры данных", "algorithms", "leetcode", "codeforces", "олимпиад", "big-o", "асимптотик")),
    _S("git", "Git", "Основы", ("git", "гит", "github", "gitlab", "merge", "rebase")),
    _S("linux", "Linux", "Инфраструктура", ("linux", "линукс", "bash", "shell", "unix", "ubuntu")),
    _S("docker", "Docker", "Инфраструктура", ("docker", "докер", "контейнер", "docker-compose", "compose")),
    _S("kubernetes", "Kubernetes", "Инфраструктура", ("kubernetes", "k8s", "кубер", "helm")),
    _S("ci_cd", "CI/CD", "Инфраструктура", ("ci/cd", "ci", "cd", "gitlab ci", "github actions", "jenkins", "пайплайн")),
    _S("networking", "Сети", "Инфраструктура", ("tcp", "dns", "сети", "сетев", "nginx", "балансир")),
    _S("monitoring", "Мониторинг и наблюдаемость", "Инфраструктура",
       ("prometheus", "grafana", "мониторинг", "логирован", "observability", "алерт")),
    # данные и ML
    _S("pandas", "Pandas и NumPy", "Данные", ("pandas", "numpy", "dataframe", "датафрейм")),
    _S("statistics", "Статистика", "Данные", ("статистик", "a/b", "ab-тест", "гипотез", "p-value", "statistics")),
    _S("ml", "Классическое ML", "Данные",
       ("machine learning", "машинное обучение", "sklearn", "scikit", "катбуст", "catboost", "xgboost", "ml")),
    _S("deep_learning", "Глубокое обучение", "Данные",
       ("pytorch", "tensorflow", "нейросет", "deep learning", "transformer", "трансформер", "computer vision", "nlp", "llm")),
    # QA
    _S("test_design", "Тест-дизайн", "Качество",
       ("тест-дизайн", "тест дизайн", "тест-кейс", "чек-лист", "граничн", "эквивалентн", "test design")),
    _S("test_automation", "Автоматизация тестирования", "Качество",
       ("pytest", "selenium", "playwright", "автотест", "автоматизац", "cypress", "junit")),
    _S("security", "Информационная безопасность", "Безопасность",
       ("owasp", "xss", "sql-инъекц", "csrf", "безопасност", "ctf", "pentest", "уязвим")),
]
SKILL_BY_SLUG = {s.slug: s for s in SKILLS}


# ---------------------------------------------------------------- специализации
@dataclass(frozen=True)
class Specialization:
    slug: str
    name: str
    direction: str
    description: str
    core_skills: tuple[str, ...]       # навыки, которые покрывает тест специализации
    stacks: tuple[str, ...] = ()       # варианты основного стека (опрос)
    aliases: tuple[str, ...] = ()      # для разбора текста


SPECIALIZATIONS: list[Specialization] = [
    Specialization("backend", "Бэкенд-разработка", "Разработка",
                   "Серверная логика, API, базы данных",
                   ("python", "sql", "http_api", "web_frameworks", "async", "system_design", "caching_queues",
                    "algorithms", "git", "docker", "postgresql", "linux"),
                   stacks=("python", "java", "go", "csharp", "javascript"),
                   aliases=("бэкенд", "бекенд", "backend", "back-end", "серверн", "python-разработчик",
                            "python developer", "java-разработчик", "go-разработчик")),
    Specialization("frontend", "Фронтенд-разработка", "Разработка",
                   "Клиентская часть веб-приложений",
                   ("javascript", "typescript", "react", "html_css", "browser", "http_api", "algorithms", "git"),
                   stacks=("javascript", "typescript"),
                   aliases=("фронтенд", "фронт", "frontend", "front-end", "react-разработчик", "верстальщик")),
    Specialization("data_science", "Data Science и ML", "Данные и ИИ",
                   "Модели машинного обучения и анализ данных",
                   ("python", "pandas", "statistics", "ml", "deep_learning", "sql", "algorithms"),
                   stacks=("python",),
                   aliases=("data scientist", "data science", "ml-инженер", "ml engineer", "машинн",
                            "дата-сайентист", "ds-", "nlp-инженер", "cv-инженер", "аналитик данных",
                            "аналитики данных", "data analyst", "аналитика данных")),
    Specialization("devops", "DevOps / SRE", "Инфраструктура",
                   "Инфраструктура, CI/CD, эксплуатация",
                   ("linux", "docker", "kubernetes", "ci_cd", "networking", "monitoring", "git", "python"),
                   stacks=("python", "go"),
                   aliases=("devops", "девопс", "sre", "инженер инфраструктуры", "системный администратор",
                            "platform engineer")),
    Specialization("qa", "Тестирование (QA)", "Качество",
                   "Ручное и автоматизированное тестирование",
                   ("test_design", "test_automation", "python", "sql", "http_api", "git", "security"),
                   stacks=("python", "java", "javascript"),
                   aliases=("qa", "тестировщик", "тестирован", "aqa", "sdet", "автотестировщик")),
]
SPEC_BY_SLUG = {s.slug: s for s in SPECIALIZATIONS}

# Смежные специализации: частичный зачёт при подборе (работодатель может разрешить)
ADJACENT_SPECS: dict[str, tuple[str, ...]] = {
    "backend": ("devops", "data_science"),
    "frontend": ("backend",),
    "data_science": ("backend",),
    "devops": ("backend",),
    "qa": ("backend",),
}

# ---------------------------------------------------------------- прочее
INDUSTRIES = [
    {"slug": "fintech", "name": "Финтех и банки"},
    {"slug": "ecommerce", "name": "E-commerce и ритейл"},
    {"slug": "govtech", "name": "Госсектор"},
    {"slug": "telecom", "name": "Телеком"},
    {"slug": "industry", "name": "Промышленность"},
    {"slug": "gamedev", "name": "Геймдев"},
    {"slug": "edtech", "name": "Образование"},
    {"slug": "healthtech", "name": "Медицина"},
    {"slug": "media", "name": "Медиа и развлечения"},
    {"slug": "security", "name": "Кибербезопасность"},
    {"slug": "other", "name": "Другое"},
]

WORK_FORMATS = [
    {"slug": "office", "name": "Офис"},
    {"slug": "hybrid", "name": "Гибрид"},
    {"slug": "remote", "name": "Удалённо"},
]

ROLES = [
    {"slug": "individual", "name": "Индивидуальный разработчик"},
    {"slug": "team_lead", "name": "Тимлид"},
    {"slug": "mentor", "name": "Наставник"},
    {"slug": "architect", "name": "Архитектор"},
    {"slug": "captain", "name": "Капитан команды на соревнованиях"},
]

SOFT_SKILLS = ["Коммуникация", "Работа в команде", "Лидерство", "Самоорганизация", "Наставничество",
               "Публичные выступления", "Решение конфликтов", "Тайм-менеджмент"]

# Структурированные причины отказа: из них строится обратная связь сторонам (механика п.4 команды)
DECLINE_REASONS = [
    {"slug": "salary_low", "name": "Зарплата ниже ожиданий", "side": "employer"},
    {"slug": "stack_mismatch", "name": "Не подходит стек или задачи", "side": "employer"},
    {"slug": "grade_mismatch", "name": "Уровень позиции не соответствует моему", "side": "employer"},
    {"slug": "format_mismatch", "name": "Не подходит формат работы или город", "side": "employer"},
    {"slug": "company", "name": "Не интересна компания или отрасль", "side": "employer"},
    {"slug": "not_looking", "name": "Сейчас не ищу работу", "side": "candidate"},
    {"slug": "other", "name": "Другое", "side": "candidate"},
]
DECLINE_REASON_SLUGS = {r["slug"] for r in DECLINE_REASONS}


def as_dict() -> dict:
    """Весь справочник одним объектом — отдаётся фронтенду."""
    return {
        "grades": [{k: v for k, v in g.items() if k != "cut"} | {"cut": g["cut"] if g["cut"] > -50 else None}
                   for g in GRADES],
        "skills": [{"slug": s.slug, "name": s.name, "group": s.group} for s in SKILLS],
        "specializations": [
            {"slug": s.slug, "name": s.name, "direction": s.direction, "description": s.description,
             "core_skills": list(s.core_skills), "stacks": list(s.stacks)} for s in SPECIALIZATIONS
        ],
        "industries": INDUSTRIES,
        "work_formats": WORK_FORMATS,
        "roles": ROLES,
        "soft_skills": SOFT_SKILLS,
        "decline_reasons": DECLINE_REASONS,
    }
