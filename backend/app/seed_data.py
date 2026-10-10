"""Демо-контент: компании, описания вакансий (на их основе показываем формирование тестов), регулярные задания."""

COMPANIES = [
    {"email": "employer@demo.ru", "name": "ТехноПлатформа", "industry": "fintech", "city": "Москва", "size": "500–1000",
     "website": "https://example.org/technoplatforma",
     "description": "Платёжная инфраструктура для малого бизнеса: эквайринг, онлайн-кассы, API для маркетплейсов.",
     "contact_name": "Мария Соколова", "contact_telegram": "@techno_hr"},
    {"email": "hr@neurolab.demo", "name": "НейроЛаб", "industry": "healthtech", "city": "Санкт-Петербург", "size": "50–200",
     "description": "Компьютерное зрение для медицинской диагностики: анализ снимков, помощь врачам."},
    {"email": "hr@gosuslugi-tech.demo", "name": "ЦифраГород", "industry": "govtech", "city": "Казань", "size": "200–500",
     "description": "Цифровые сервисы для городского хозяйства: заявки жителей, мониторинг транспорта."},
    {"email": "hr@shopflow.demo", "name": "ШопФлоу", "industry": "ecommerce", "city": "Москва", "size": "1000+",
     "description": "Маркетплейс товаров для дома: 3 млн заказов в месяц, собственная логистика."},
    {"email": "hr@secureline.demo", "name": "Защищённая Линия", "industry": "security", "city": "Новосибирск",
     "size": "50–200", "description": "Сервисы защиты веб-приложений и мониторинга инцидентов ИБ."},
]

# Описания вакансий — исходный текст разбирается автоматически (правила/LLM) в структуру, по которой
# строится и подборка, и чертёж теста под вакансию.
VACANCIES = [
    ("employer@demo.ru", "Middle Python-разработчик (платёжный шлюз)", """Ищем Middle Python-разработчика в команду платёжного шлюза.
Задачи: развитие API приёма платежей, интеграции с банками, оптимизация запросов к PostgreSQL.
Стек: Python 3.12, FastAPI, PostgreSQL, Redis, Docker. Опыт от 2 лет.
Будет плюсом: Kafka, Kubernetes, понимание асинхронности.
Зарплата 250 000 – 340 000 ₽, гибрид или удалённо, Москва.""", "middle"),
    ("employer@demo.ru", "Senior DevOps-инженер", """Senior DevOps / SRE в платформенную команду.
Kubernetes (свои кластеры), CI/CD на GitLab CI, мониторинг Prometheus/Grafana, Linux, сети, Docker.
Нужно выстроить SLO и бюджет ошибок для 40 сервисов. Опыт от 4 лет.
Будет плюсом: Python или Go для автоматизации.
Вилка 380 000 – 480 000 ₽, удалённо.""", "senior"),
    ("hr@neurolab.demo", "Data Scientist (компьютерное зрение)", """Middle Data Scientist в команду CV.
Обучение и валидация моделей сегментации снимков: PyTorch, классическое ML для табличных признаков, pandas, статистика.
Python обязателен, SQL — для выгрузок. Будет плюсом: опыт с медицинскими данными, A/B-тесты.
Зарплата от 230 000 до 300 000 руб, Санкт-Петербург, гибрид.""", "middle"),
    ("hr@shopflow.demo", "Senior Frontend-разработчик (React)", """Senior Frontend в команду витрины маркетплейса.
React, TypeScript, производительность рендеринга, браузерные API, вёрстка HTML/CSS без UI-кита.
Опыт от 5 лет. Будет плюсом: Next.js, опыт A/B-экспериментов.
350 000 – 450 000 ₽, офис или гибрид, Москва.""", "senior"),
    ("hr@shopflow.demo", "Junior QA Automation", """Junior QA-инженер (автоматизация).
Пишем автотесты API и UI на Python: pytest, Playwright. Тест-дизайн, SQL для проверки данных, Git.
Можно без коммерческого опыта, но с пет-проектами. Будет плюсом: понимание HTTP и REST.
Зарплата 90 000 – 130 000 ₽, удалённо.""", "junior"),
    ("hr@gosuslugi-tech.demo", "Junior бэкенд-разработчик (Python)", """Junior Python-разработчик в команду городских сервисов.
Django, PostgreSQL, REST API, Git, Linux. Наставник в команде, код-ревью.
Будет плюсом: Docker и алгоритмическая подготовка (олимпиады, спортивное программирование).
Зарплата 110 000 – 150 000 ₽, офис, Казань.""", "junior"),
    ("hr@secureline.demo", "Middle QA (безопасность веб-приложений)", """Middle QA со знанием безопасности веб-приложений.
Тест-дизайн, тестирование API (HTTP/REST), OWASP Top 10, SQL-инъекции, XSS. Автотесты на Python.
Будет плюсом: участие в CTF.
Зарплата 180 000 – 240 000 ₽, удалённо.""", "middle"),
]

NEEDS = [
    ("employer@demo.ru", "Middle Python в платёжный сервис", """Нужен Middle Python-разработчик в платёжный сервис.
Обязательно: Python, SQL, PostgreSQL, Docker, HTTP API. Будет плюсом: Kafka/Redis, асинхронность.
Вилка 250 000 – 340 000 ₽, гибрид или удалёнка."""),
    ("employer@demo.ru", "Senior DevOps для платформенной команды", """Ищем Senior DevOps: Kubernetes, CI/CD, Linux, мониторинг, сети. Будет плюсом: Python.
Удалённо, 380–480 тыс."""),
    ("hr@neurolab.demo", "Data Scientist в команду CV", """Data Scientist middle: Python, pandas, статистика, машинное обучение, PyTorch. Будет плюсом: SQL. 230-300 тыс, гибрид"""),
    ("hr@shopflow.demo", "Senior Frontend витрины", """Senior фронтенд: React, TypeScript, JavaScript, вёрстка HTML/CSS, браузер. Будет плюсом: алгоритмы. 350 000 – 450 000 ₽"""),
    ("hr@shopflow.demo", "Junior QA Automation", """Junior QA automation: тест-дизайн, pytest, автоматизация, SQL, git. Будет плюсом: HTTP API. 90-130 тыс, удалённо"""),
    ("hr@secureline.demo", "Middle QA (безопасность)", """Middle QA: тест-дизайн, безопасность (OWASP, XSS, SQL-инъекции), HTTP API, Python. 180 000 – 240 000 ₽ удалённо"""),
]

TASKS = [
    ("employer@demo.ru", "Идемпотентность платежей", "backend", ["system_design", "http_api"], "junior",
     "Клиент отправляет POST /payments и при таймауте повторяет запрос. Как гарантировать, что платёж не спишется "
     "дважды? Опишите подход: что хранится в БД, какие ограничения, что вернуть на повтор.",
     [{"criterion": "Ключ идемпотентности от клиента", "keywords": ["идемпотент", "idempotency", "ключ"], "weight": 2},
      {"criterion": "Уникальное ограничение/индекс в БД", "keywords": ["уникальн", "unique", "индекс"], "weight": 1},
      {"criterion": "Возврат сохранённого результата при повторе", "keywords": ["сохран", "тот же ответ", "повтор"], "weight": 1},
      {"criterion": "Транзакция/блокировка при гонке", "keywords": ["транзакц", "блокиров", "lock", "гонк"], "weight": 1}]),
    ("employer@demo.ru", "Медленный эндпоинт", "backend", ["postgresql", "sql"], "middle",
     "Эндпоинт GET /merchants/{id}/payments?from=&to= стал отвечать 3 секунды на 50 млн строк. Как будете искать и "
     "устранять причину?",
     [{"criterion": "EXPLAIN ANALYZE / план запроса", "keywords": ["explain", "план"], "weight": 2},
      {"criterion": "Составной индекс под фильтр и сортировку", "keywords": ["индекс", "index"], "weight": 2},
      {"criterion": "Пагинация / ограничение выборки", "keywords": ["пагинац", "limit", "keyset", "курсор"], "weight": 1},
      {"criterion": "Партиционирование/архив", "keywords": ["партиц", "partition", "архив"], "weight": 1}]),
    ("employer@demo.ru", "Падающий под нагрузкой под", "devops", ["kubernetes", "monitoring"], "middle",
     "Под сервиса раз в час перезапускается с OOMKilled. Опишите план диагностики и исправления.",
     [{"criterion": "Метрики памяти/профилирование", "keywords": ["метрик", "prometheus", "профил", "grafana"], "weight": 2},
      {"criterion": "requests/limits", "keywords": ["limit", "request", "лимит"], "weight": 2},
      {"criterion": "Поиск утечки", "keywords": ["утечк", "leak"], "weight": 1}]),
    ("hr@shopflow.demo", "Тормозит список товаров", "frontend", ["react", "browser"], "middle",
     "Страница с 5000 карточек товаров тормозит при прокрутке. Что сделаете?",
     [{"criterion": "Виртуализация списка", "keywords": ["виртуализ", "virtual", "windowing"], "weight": 2},
      {"criterion": "Мемоизация / лишние перерисовки", "keywords": ["memo", "мемо", "перерисов", "ререндер"], "weight": 1},
      {"criterion": "Профилирование", "keywords": ["profiler", "профил", "performance"], "weight": 1}]),
]

ABOUT = {
    "backend": ["Разрабатываю API и сервисы обработки данных, люблю PostgreSQL и чистую архитектуру.",
                "Бэкенд на Python, интеграции с внешними системами, оптимизация запросов.",
                "Пишу высоконагруженные сервисы, интересуюсь распределёнными системами."],
    "frontend": ["Делаю интерфейсы на React и TypeScript, слежу за производительностью.",
                 "Фронтенд, дизайн-системы, доступность интерфейсов."],
    "data_science": ["Строю модели ML для табличных данных и CV, довожу до продакшена.",
                     "Анализ данных и классическое машинное обучение, A/B-тесты."],
    "devops": ["Kubernetes, CI/CD, мониторинг — автоматизирую всё, что повторяется дважды.",
               "Эксплуатация и надёжность сервисов, SRE-практики."],
    "qa": ["Тестирую API и веб-интерфейсы, пишу автотесты на pytest.",
           "QA с уклоном в автоматизацию и безопасность веб-приложений."],
}
