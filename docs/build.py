"""Сборка сопроводительной документации: Markdown + результаты валидации → HTML → PDF.

    python docs/build.py            # нужен markdown; для PDF — playwright с Chromium
Результат: docs/build/documentation.md (с подставленными результатами), .html, .pdf
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VAL = ROOT / "validation" / "out"
BUILD = DOCS / "build"
BUILD.mkdir(exist_ok=True)


def pct(x: float) -> str:
    if 0 < x < 0.05:
        return f"{x * 100:.1f}%".replace(".", ",")
    return f"{x * 100:.0f}%"


def f3(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def validation_section() -> str:
    t = json.loads((VAL / "testing_results.json").read_text())
    m = json.loads((VAL / "matching_results.json").read_text())
    p = json.loads((VAL / "parsing_results.json").read_text())
    o, disc, leak, comp = t["overall"], t["discrimination"], t["leakage"], t["comparability"]
    n_spec = next(iter(t["per_spec"].values()))["n"]
    spec_names = {"backend": "Бэкенд", "frontend": "Фронтенд", "data_science": "Data Science", "devops": "DevOps", "qa": "QA"}
    rows_spec = "\n".join(
        f"| {spec_names[s]} | {v['pool']} | {pct(v['decision_accuracy'])} | {pct(v['decision_accuracy_far_from_cut'])} | "
        f"{pct(v['retest_agreement'])} | {f3(v['retest_kappa'])} | {pct(v['final_category_exact'])} | {pct(v['final_category_retest_agreement'])} | {v['mean_len']:.1f} |"
        for s, v in t["per_spec"].items())
    ours = leak["ours"]
    res = m["results"]
    order = list(res)
    rows_match = "\n".join(
        f"| {name} | {pct(res[name]['P@10']['mean'])} ({pct(res[name]['P@10']['ci95'][0])}–{pct(res[name]['P@10']['ci95'][1])}) | "
        f"{f3(res[name]['nDCG@10']['mean'])} | {f3(res[name]['MRR']['mean'])} | {pct(res[name]['P@20']['mean'])} |"
        for name in order)
    sens = m["sensitivity_p10"]
    sens_rows = "\n".join(f"| {lvl} | {pct(v['Ключевые слова резюме'])} | {pct(v['Только категория по тесту'])} | {pct(v['Наш ранжировщик (полный)'])} |"
                          for lvl, v in sens.items())
    lt = m["ltr"]
    pr, pn = p["resume"], p["needs"]
    studies = "\n".join(f"| {s['label']} | {pct(s['decision_accuracy'])} | {pct(s['retest_agreement'])} | {f3(s['theta_corr'])} |"
                        for s in comp["studies"])
    cal = comp["calibration"]
    return f"""
Готовых датасетов и эталонной разметки в рамках хакатона нет. Поэтому основная процедура — **симуляция с
известной истиной**. У каждого синтетического кандидата есть скрытый «истинный» уровень θ и уровни по
навыкам. Он проходит **тот же код** адаптивного теста и ранжирования, что работает в продукте, а ответы
генерируются моделью 3PL с параметрами, которые **отличаются** от известных системе (экспертная оценка
трудности ошибается в среднем на 0,33, дискриминативность — на 25%). Для экземпляров одного шаблона заложен
разброс трудности. Это проверяет механику в условиях, когда эксперт ошибся, а изоморфные варианты не идеально
равны. Всё воспроизводится: `validation/testing_study.py`, `matching_study.py`, `parsing_study.py`,
фиксированные seed.

Ограничение честно: симуляция проверяет механику, а не содержание конкретных заданий. Проверка на живых
людях описана в п. 6.6.

### 6.1. Тестирование: точность, повторяемость, дискриминативность

Кандидаты: {n_spec} на каждую из 5 специализаций, θ ~ N(0,15; 1). Заявленный грейд — истинный с типичной
переоценкой (+0,25 ± 0,5). Каждый кандидат проходит тест **дважды** с новыми заданиями и экземплярами.
Порог решения — пройден ли заявленный грейд; «вдали от порога» — |θ − порог| ≥ 0,3. Итоговая категория —
весь путь как в продукте: тест → принять грейд ниже или тест ниже с учётом ответов первой попытки.

| Специализация | Шаблонов | Точность решения | вдали от порога | Повторяемость решения | κ Коэна | Итоговая категория = истинной | Повторяемость категории | Заданий в тесте |
|---|---|---|---|---|---|---|---|---|
{rows_spec}
| **Среднее** | | **{pct(o['decision_accuracy'])}** | **{pct(o['decision_accuracy_far_from_cut'])}** | **{pct(o['retest_agreement'])}** | **{f3(o['retest_kappa'])}** | **{pct(o['final_category_exact'])}** | **{pct(o['final_category_retest_agreement'])}** | **{o['mean_len']:.1f}** |

- Итоговая категория отличается от истинной **не более чем на один грейд в {pct(o['final_category_within1'])}** случаев.
- Корреляция оценки θ̂ с истинным уровнем — **{f3(o['theta_corr'])}**, RMSE {f3(o['theta_rmse'])}. Между двумя
  независимыми прохождениями — {f3(o['retest_theta_corr'])}.
- Ложные «сдал» среди тех, кто ниже порога, — {pct(o['false_pass'])}, ложные «не сдал» — {pct(o['false_fail'])}.
  Ошибки сосредоточены у самого порога: там любой тест конечной длины близок к монетке.
- **Дискриминативность заданий.** Точечно-бисериальная корреляция успеха в задании с итоговой оценкой: медиана
  **{f3(disc['point_biserial_median'])}**, выше 0,2 у **{pct(disc['share_above_0_2'])}** шаблонов, выше 0,3 у
  {pct(disc['share_above_0_3'])} (оценено {disc['items_evaluated']} шаблонов с ≥ 30 ответами). Слабые
  шаблоны видны администратору и выводятся из банка. Разделение слабых и сильных относительно порога —
  ROC-AUC {f3(o['auc_weak_vs_strong'])}.
- **Ложные флаги person-fit** у честных кандидатов — {pct(o['honest_flagged_share'])}.

![Операционные характеристики](../../validation/out/fig_oc.png)

*Вероятность сдать тест в зависимости от истинного уровня. Чем круче кривая у порога, тем лучше тест
разделяет кандидатов; пунктир — идеальная ступенька.*

![Оценка и истинный уровень](../../validation/out/fig_recovery.png)

*Оценка теста против истинного уровня. Ошибки решения (розовые точки) — у вертикальных линий порогов.*

Конфигурация теста выбрана по симуляции (`validation/tune_cat.py`, `out/cat_tuning.json`). Выбор задания по
информативности у порога вместо текущей оценки и более мягкий порог уверенности дают различия в пределах
шума. Увеличение максимума с 20 до 25 заданий повышает точность вдали от порога. Ограничитель — объём
информации, а не алгоритм выбора. Поэтому дальнейший рост — за счёт более информативных заданий (ввод
ответа вместо выбора, a ≥ 1,5) и учёта ответов связанной попытки (уже сделано).

### 6.2. Устойчивость к распространению заданий

**Атака.** Платформа работает: {leak['dump_candidates']} честных кандидатов проходят тест на Middle по бэкенду,
система ведёт журнал показанных экземпляров. Затем **все** их задания с правильными ответами
({leak['dump_instances']} экземпляров) сливаются в общую базу. Слабый кандидат (истинный уровень на 0,6 ниже
порога Middle) проходит тест и отвечает верно на всё, что находит в базе, остальное — по своим силам.

| Сценарий | Доля сдавших Middle | Доля заданий, найденных в слитой базе |
|---|---|---|
| Единый тест для всех, без утечки | {pct(leak['static_form']['no_leak']['pass_rate'])} | — |
| Единый тест для всех, ответы слиты | **{pct(leak['static_form']['leak']['pass_rate'])}** | 100% |
| Наш тест, без утечки | {pct(ours['no_leak']['pass_rate'])} | {pct(ours['no_leak']['dump_hit_rate'])} |
| Наш тест, слив, только параметрические шаблоны (без журнала показов и лимитов) | {pct(ours['leak_no_defense']['pass_rate'])} | {pct(ours['leak_no_defense']['dump_hit_rate'])} |
| **Наш тест, слив, все защиты** | **{pct(ours['leak']['pass_rate'])}** | {pct(ours['leak']['dump_hit_rate'])} |

Итог: прирост доли сдавших от слива — **+{(ours['leak']['pass_rate'] - ours['no_leak']['pass_rate']) * 100:.0f} п. п.** против
+{(leak['static_form']['leak']['pass_rate'] - leak['static_form']['no_leak']['pass_rate']) * 100:.0f} п. п. у единого теста. Два случайных
кандидата получают задания одних и тех же шаблонов в {pct(leak['template_overlap_mean'])} случаев, но один и тот же
**экземпляр** — в {leak['instance_overlap_mean'] * 100:.1f}% случаев. Медиана различных экземпляров на шаблон —
{leak['variant_space_median']} (на 1500 seed; у большинства — практически без ограничений).

Остаточный эффект — от вопросов на понимание с небольшим пулом сценариев ({leak['templates_with_lt_20_variants']}
из {leak['templates_total']} шаблонов бэкенда): их допускается не больше одного на тест. Расширение этих пулов
перефразированием через LLM с калибровкой — следующий шаг.

![Утечки](../../validation/out/fig_leak.png)

### 6.3. Сопоставимость сложности и калибровка

Пул бэкенда, {cal['n_respondents']} симулированных прохождений ({cal['responses']} ответов) плюс по три
незачётных претест-задания на кандидата. Параметры шаблонов оцениваются EM-алгоритмом маргинального
правдоподобия.

- Трудность: корреляция с истинной — экспертная оценка **{f3(cal['b_corr_expert'])}**, после калибровки
  **{f3(cal['b_corr_calibrated'])}**. RMSE {f3(cal['b_rmse_expert'])} → {f3(cal['b_rmse_calibrated'])}.
- Дискриминативность после калибровки: корреляция с истинной {f3(cal['a_corr_calibrated'])}.

| Условие | Точность решения | Повторяемость | Корр. θ̂ и θ |
|---|---|---|---|
{studies}

«Уникальные задания без калибровки» моделируют подход «нейросеть генерирует задания под каждого»: трудность
каждого экземпляра отклоняется от предполагаемой со стандартным отклонением 0,7. В этой симуляции разница в
точности решения невелика: адаптивный тест частично компенсирует случайный разброс. Но такой подход теряет
главное — **измеримость**: трудность задания неизвестна, её нельзя проверить, а у кандидатов оказываются
разные «линейки». В подходе с шаблонами трудность известна и уточняется по данным. Калибровка повышает
точность оценки уровня (корреляция θ̂ с истинным уровнем растёт к верхней границе — идеально известным
параметрам). Различия в точности решения о грейде между строками таблицы — в пределах шума выборки
(500 кандидатов), их проверит пилот на реальных ответах.

![Калибровка](../../validation/out/fig_calibration.png)

### 6.4. Подбор на наборе пар «вакансия — кандидат»

Мир: {m['candidates']} кандидатов с категорией (прошли тот же адаптивный тест; доля категорий, совпавших с
истинным грейдом, — {pct(m['grade_accuracy'])}) и {m['vacancies']} вакансий (специализация, грейд, 3–4
обязательных навыка, вилка, формат). **Эталонная релевантность** пары считается по скрытым истинным навыкам и
грейду, зарплатным ожиданиям и формату. Кандидат на грейд выше подходит, если сходятся деньги. Ни один
ранжировщик эталон не видит. Резюме моделируются с типичной переоценкой: метаанализ Mabe & West (1982) даёт
среднюю корреляцию самооценки способностей с измеренными ≈ 0,29. Основной сценарий — корреляция около 0,45.
Релевантен = эталон ≥ 2 из 3.

| Метод | P@10 (95% ДИ) | nDCG@10 | MRR | P@20 |
|---|---|---|---|---|
{rows_match}

**Доля релевантных кандидатов в топ-10 — {pct(res['Наш ранжировщик (полный)']['P@10']['mean'])}** против
{pct(res['Ключевые слова резюме']['P@10']['mean'])} у поиска по ключевым словам резюме и заявленному опыту
(так работают универсальные площадки). Вклады слагаемых: одна категория по тесту без ранжирования даёт
{pct(res['Только категория по тесту']['P@10']['mean'])}, ранжирование по оценкам навыков с объяснением —
основной прирост.

Достижения ФСП в этой симуляции почти не меняют точность (с ними и без них в пределах доверительного
интервала): в модели мира они коррелируют с тем же уровнем, который уже измерил тест. Их ценность —
независимое внешнее подтверждение (защита от списывания, доверие работодателя) и сигнал для кандидатов, у
которых мало ответов по навыку. Её покажет только живая эксплуатация.

**Чувствительность к честности резюме (P@10):**

| Резюме | Ключевые слова | Только категория | Наш ранжировщик |
|---|---|---|---|
{sens_rows}

Даже при почти честных резюме ранжирование по подтверждённым навыкам лучше. По мере роста «раздувания»
резюме разрыв растёт: тест не зависит от того, что человек о себе написал.

![Подбор](../../validation/out/fig_matching.png)

**Дообучение на исходах приглашений.** Скрытая модель решения кандидата в симуляции придаёт деньгам и формату
больший вес, чем экспертные веса. На {lt['train_samples']} исходах приглашений половины вакансий веса дообучены;
проверка — на другой половине:

| | Экспертные веса | Дообученные |
|---|---|---|
| ROC-AUC предсказания согласия (отложенная выборка) | {f3(lt['auc_holdout_default'])} | {f3(lt['auc_holdout_new'])} |
| Ожидаемая доля принятых приглашений в топ-10 | {pct(lt['expected_accept_top10_default'])} | **{pct(lt['expected_accept_top10_learned'])}** |
| P@10 по эталону релевантности | {pct(lt['p10_default'])} | **{pct(lt['p10_learned'])}** |

Нижняя граница для весов факторов соответствия (80% экспертных) не даёт модели «купить» согласие ценой
релевантности. В эксперименте выросли обе метрики.

""" + text_methods_section(pr, pn)


METHOD_NAMES = {"rules": "Правила", "llm": "LLM", "hybrid": "Гибрид"}
RESUME_ROWS = [("full_name", "ФИО"), ("email", "Email"), ("phone", "Телефон"), ("telegram", "Telegram"),
               ("city", "Город"), ("years_experience", "Стаж (±0,5 года)"), ("specialization", "Специализация")]
NEED_ROWS = [("specialization", "Специализация"), ("grades_exact", "Грейд"), ("salary", "Зарплатная вилка"),
             ("formats", "Формат работы"), ("city", "Город")]


def plural(n: int, forms: tuple[str, str, str]) -> str:
    a, b = abs(n) % 100, abs(n) % 10
    form = forms[2] if 10 < a < 20 else forms[1] if 1 < b < 5 else forms[0] if b == 1 else forms[2]
    return f"{n} {form}"


def short_model(mid: str) -> str:
    base = mid.replace("\\", "/").split("/")[-1]
    base = re.sub(r"(?i)[-_.]?gguf", "", base)
    return base[:40]


def text_runs() -> tuple[dict, list[dict]]:
    rules = json.loads((VAL / "llm_compare_rules.json").read_text(encoding="utf-8"))
    runs = []
    for f in sorted(VAL.glob("llm_compare_*.json")):
        if f.name != "llm_compare_rules.json":
            runs.append(json.loads(f.read_text(encoding="utf-8")))
    return rules, runs


def text_methods_table(base: dict, runs: list[dict]) -> str:
    """Столбцы: правила (из base), затем LLM и гибрид для каждой модели. Все прогоны — на одном наборе."""
    cols = [("Правила", base, "rules")]
    for r in runs:
        nm = short_model(r["model"])
        cols += [(f"LLM: {nm}", r, "llm"), (f"Гибрид: {nm}", r, "hybrid")]
    head = "| | " + " | ".join(c[0] for c in cols) + " |\n|---|" + "---|" * len(cols) + "\n"
    blank = " |" * len(cols)

    def row(label, get):
        return f"| {label} | " + " | ".join(get(d, m) for _, d, m in cols) + " |"

    out = [f"| **Резюме ({base['resume']['rules']['n']})** |{blank}"]
    out += [row(lbl, lambda d, m, f=f: pct(d["resume"][m]["fields"][f])) for f, lbl in RESUME_ROWS]
    out += [row("Навыки, F1", lambda d, m: f3(d["resume"][m]["skills"]["f1"])),
            row("**Все поля без ошибок**", lambda d, m: f"**{pct(d['resume'][m]['all_fields_ok'])}**")]
    out += [f"| **Потребности ({base['needs']['rules']['n']})** |{blank}"]
    out += [row(lbl, lambda d, m, f=f: pct(d["needs"][m][f])) for f, lbl in NEED_ROWS]
    out += [row("Навыки, F1", lambda d, m: f3(d["needs"][m]["skills"]["f1"])),
            row("Обязательный / желательный", lambda d, m: pct(d["needs"][m]["must_nice_placement"]))]
    out += [f"| **Оценка ответов ({plural(base['rubric']['rules']['n_answers'], ('ответ', 'ответа', 'ответов'))}, "
            f"{plural(base['rubric']['rules']['n_criteria'], ('отметка', 'отметки', 'отметок'))})** |{blank}"]
    out += [row("Отметки «выполнен / нет» верны", lambda d, m: pct(d["rubric"][m]["criteria_accuracy"])),
            row("κ Коэна с эталоном", lambda d, m: f3(d["rubric"][m]["kappa"]) if d["rubric"][m]["kappa"] is not None else "—"),
            row("Ошибка балла 0–10 (MAE)", lambda d, m: f"{d['rubric'][m]['score_mae']:.1f}".replace(".", ","))]
    if runs:
        def tm(d, m, kind):
            if m == "rules":
                return "< 0,1 с"
            t = (d.get("timing") or {}).get(kind)
            return f"{t['seconds_mean']:.0f} с".replace(".", ",") if t else "—"
        out += [f"| **Время на текст** |{blank}",
                row("Резюме", lambda d, m: tm(d, m, "resume")),
                row("Потребность", lambda d, m: tm(d, m, "need")),
                row("Ответ на задание", lambda d, m: tm(d, m, "answer"))]
    return head + "\n".join(out)


def llm_conclusion(m: dict) -> str:
    """Выводы по прогону с моделью. Числа — из файла результатов, формулировки — по разбору ошибок."""
    R, L, H = (m["resume"][k] for k in ("rules", "llm", "hybrid"))
    NR, NL, NH = (m["needs"][k] for k in ("rules", "llm", "hybrid"))
    BR, BL = m["rubric"]["rules"], m["rubric"]["llm"]
    t = m["timing"]
    tps = t["resume"].get("tokens_per_second")
    invalid = sum(round(v["invalid_share"] * v["n"]) for v in t.values())
    calls = sum(v["n"] for v in t.values())
    model = m["model"].split("/")[-1]
    fig = (VAL / "fig_text_methods.png").exists()
    sec = lambda x: f"{x:.0f}"  # noqa: E731
    dec = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
    return f"""Модель — `{model}` в llama.cpp на компьютере команды с GTX 1650 (4 ГБ), генерация около
{tps:.0f} токенов в секунду. Из {calls} ответов модели не разобран {"ни один" if invalid == 0 else invalid}.
""" + ("""
![Правила, LLM и гибрид на отложенном наборе](../../validation/out/fig_text_methods.png)
""" if fig else "") + f"""
**Где модель сильнее правил — везде, где нужно понимание текста.** ФИО {pct(R['fields']['full_name'])} →
{pct(L['fields']['full_name'])} (резюме на английском), город {pct(R['fields']['city'])} → {pct(L['fields']['city'])}
(любой город, а не только справочник), специализация {pct(R['fields']['specialization'])} →
{pct(L['fields']['specialization'])}. В потребностях: грейд {pct(NR['grades_exact'])} → {pct(NL['grades_exact'])}, формат
работы {pct(NR['formats'])} → {pct(NL['formats'])}, вилка {pct(NR['salary'])} → {pct(NL['salary'])}. Резюме без единой
ошибки — {pct(R['all_fields_ok'])} → **{pct(H['all_fields_ok'])}** в гибриде. Сильнее всего разница в оценке ответов:
отметки «критерий выполнен» верны в {pct(BR['criteria_accuracy'])} → **{pct(BL['criteria_accuracy'])}** случаев
(κ {f3(BR['kappa'])} → {f3(BL['kappa'])}), ошибка балла {dec(BR['score_mae'])} → **{dec(BL['score_mae'])}** из 10. Модель
отличает верную мысль своими словами от термина, употреблённого мимо; её ошибки — в основном снисходительность к
неполным ответам ({BL['false_met']} ложных «выполнен» на {BL['n_criteria'] if 'n_criteria' in BL else 128} отметок).

**Где модель не помогает.** Контакты — по 100% у обоих методов, в продукте они всё равно берутся регулярными
выражениями. Навыки: модель точнее (точность {f3(L['skills']['precision'])} против {f3(R['skills']['precision'])}), но
пропускает навыки, не названные технологией («проектирование API», «асинхронность», «тест-дизайн»): полнота
{f3(L['skills']['recall'])} против {f3(R['skills']['recall'])}. В резюме гибрид объединяет оба списка и сохраняет
полноту правил (F1 {f3(H['skills']['f1'])}); в потребностях берёт навыки модели, F1 {f3(NH['skills']['f1'])} — на
уровне правил ({f3(NR['skills']['f1'])}). Стаж — {pct(R['fields']['years_experience'])} у обоих, но ошибаются они на
разных резюме: правила — когда стаж нужно сложить из нескольких периодов или резюме на английском, модель — в
арифметике дат (чаще занижает стаж); сменившие профессию сбивают обоих.

**Цена — время.** На этом компьютере модель тратит на резюме в среднем {sec(t['resume']['seconds_mean'])} с (она
переписывает и опыт работы — около {t['resume']['completion_tokens_mean']:.0f} токенов ответа), на потребность
{sec(t['need']['seconds_mean'])} с, на ответ на задание {sec(t['answer']['seconds_mean'])} с; правила — доли секунды.
Поэтому в продукте медленные вызовы фоновые: черновик анкеты по правилам появляется сразу, а модель уточняет его
в течение минуты и не трогает поля, которые кандидат уже исправил; балл за ответ сначала считается по ключевым
словам и уточняется моделью следом. Разбор потребности работодатель ждёт; если модель не ответила за 45 с —
работают правила.

**Вывод.** LLM — опция развёртывания, а не зависимость: без неё платформа полностью работает на правилах с
качеством из таблицы выше, с локальной моделью на сервере заказчика точнее разбор текстов и заметно точнее
автооценка ответов. Тексты при этом не покидают сервер.

**Что исправить по итогам разбора ошибок.** Этот набор уже использован для анализа, поэтому эффект доработок
проверяется на новых текстах.

1. Город из ответа модели приводить к справочнику, как навыки. Все ошибки модели по городу в потребностях — верный
   город, записанный по-английски или сокращённо («Moscow», «СПб»): в разметке резюме варианты написания
   засчитывались, в потребностях — нет.
2. Если модель явно ответила «не указано» (верхняя граница вилки, город), не подставлять значение правил: на этом
   гибрид в потребностях уступил модели по одному тексту в вилке и в городе.
3. Стаж считать в коде по периодам работы, которые выделила модель, а не просить модель складывать даты.
4. Навыки потребности объединять с найденными правилами, как в резюме, с учётом отрицаний («1С не нужен»)."""


def text_methods_section(pr: dict, pn: dict) -> str:
    rules, runs = text_runs()
    rr, rn, rb = rules["resume"]["rules"], rules["needs"]["rules"], rules["rubric"]["rules"]
    full = [r for r in runs if not r.get("partial") and r["resume"]["rules"]["n"] == rr["n"]]
    cols_note = ("\nСтолбцы «LLM» и «Гибрид» — локальная модель, методика и выводы ниже.\n" if full else "")
    cv = [rr["fields"][k] for k in ("email", "phone", "telegram")]
    contacts = f"по {pct(cv[0])}" if len(set(cv)) == 1 else f"{pct(cv[0])}, {pct(cv[1])} и {pct(cv[2])}"
    names = dict(RESUME_ROWS) | {"years_experience": "Стаж (±0,15 года)"}
    dev_rows = "\n".join(f"| {names.get(k, k)} | {pct(v)} |" for k, v in pr["field_accuracy"].items())
    if full:
        compare = f"""**Сравнение с локальной моделью.** Каждый текст отправлялся в модель **один раз**; из ответа считаются два метода. «LLM» — только
ответ модели, приведённый к справочникам (не разобранный ответ — пустой результат). «Гибрид» — так работает
продукт: поле из ответа модели, а контакты и стаж — из правил, если правила их нашли; если модель промолчала
или ответила не JSON — правила. Модели запускались локально (llama.cpp), тексты никуда не передавались.

{llm_conclusion(full[0])}"""
    else:
        compare = """**Сравнение с локальной моделью.** Скрипт `validation/llm_compare.py` (на Windows — `compare-llm.bat`)
прогоняет тот же набор через любую модель на llama.cpp (`llama-server`) или Ollama. Каждый текст
отправляется в модель один раз, из ответа считаются два метода: «LLM» — только ответ модели, приведённый к
справочникам, и «Гибрид» — как работает продукт: поле из ответа модели, контакты и стаж — из правил, если
правила их нашли; при сбое модели — правила. Результаты сравнения на видеокарте уровня GTX 1650 (4 ГБ)
будут добавлены в эту таблицу."""
    return f"""### 6.5. Разбор резюме и потребностей, автооценка заданий: правила и локальная LLM

**Реальных данных нет, поэтому проверяем как есть.** Размеченных резюме, запросов работодателей и ответов
кандидатов в рамках хакатона нет, а брать чужие резюме без согласия нельзя. Проверка — на синтетических
текстах, и цифры ниже — оценка «как есть» на этих текстах, а не обещание качества на реальном потоке.
Проверка на живых данных — п. 6.6.

**1. Набор разработки — проверка работоспособности.** {pr['n']} PDF-резюме из трёх шаблонов вёрстки и
{pn['n']} описаний потребностей. Правила писались с оглядкой на этот набор, поэтому результат заведомо
оптимистичен:

| Поле резюме | Точность |
|---|---|
{dev_rows}
| Навыки (F1) | {f3(pr['skills_f1'])} |
| Резюме без единой ошибки | {pct(pr['fully_correct_share'])} |

Потребности: специализация {pct(pn['specialization_acc'])}, грейд {pct(pn['grade_acc'])}, вилка
{pct(pn['salary_acc'])}, формат {pct(pn['formats_acc'])}, навыки — точность {f3(pn['skills_precision'])}, полнота
{f3(pn['skills_recall'])}.

**2. Отложенный набор — честная оценка.** {rr['n']} резюме, {rn['n']} описаний потребностей и
{plural(rb['n_answers'], ('ответ', 'ответа', 'ответов'))} кандидатов на 4 задания с рубриками — тексты разных стилей: выгрузка с hh.ru, резюме
на английском, студенты без опыта, сменившие профессию, сообщения тимлидов в чат, вакансии с ДМС и
отрицаниями («1С не нужен»), ответы сильные, слабые и «по ключевым словам, но мимо». Набор составлен отдельно
от правил: у автора не было доступа к словарю синонимов и коду разбора. Спорные навыки и грейды размечены
как допустимые варианты и в оценку не входят. После первого прогона правила **не подстраивались** — цифры
ниже с того прогона. Резюме идут путём продукта: PDF → pypdf → разбор. Данные: `validation/data/`.

{text_methods_table(rules, full)}
{cols_note}
Правила надёжны там, где формат жёсткий: email, телефон и Telegram — {contacts}, навыки — F1
{f3(rr['skills']['f1'])}. Слабые места — то, что требует понимания текста. Город: справочник правил знает
15 крупных городов, а кандидаты живут и в Ижевске, и в Махачкале ({pct(rr['fields']['city'])}). Стаж: его
нужно сложить из нескольких периодов работы, отделить опыт вне ИТ у сменивших профессию, понять, что у
студента его нет ({pct(rr['fields']['years_experience'])}). ФИО: почти все ошибки — в резюме на английском
({pct(rr['fields']['full_name'])}). Все поля без ошибок — только у {pct(rr['all_fields_ok'])} резюме: правку
хотя бы одного поля стоит ожидать почти всегда. Оценка ответов по ключевым словам совпадает с экспертной
разметкой в {pct(rb['criteria_accuracy'])} отметок: она не видит верную мысль своими словами и засчитывает
термин, употреблённый мимо.

{compare}

**Как это используется в продукте.** Разбор резюме — только черновик анкеты: кандидат видит каждое поле и
правит его, а **на категорию резюме не влияет**. Разбор потребности работодатель проверяет перед поиском.
Балл за ответ — подсказка: работодатель видит отметки по каждому критерию и ставит свою оценку. Поэтому
ошибка разбора стоит секунд правки, а не неверного решения о кандидате.

### 6.6. Проверка на живых данных (19–24 октября и пилот с ФСП)

1. 50–100 реальных резюме участников ФСП (с согласием), разметка двумя членами команды, согласованность
   разметчиков (κ). Сравнение правил и локальной LLM на этом наборе; правки кандидатов в черновике анкеты —
   готовая разметка для постоянного контроля качества разбора.
2. Тестирование 30–50 участников ФСП с известным уровнем (разряд, результаты, стаж) и экспертное
   собеседование вслепую. Согласие грейда по тесту с экспертным (κ Коэна, взвешенная), повторное прохождение
   через 1–2 недели для оценки стабильности на людях.
3. Калибровка параметров шаблонов по реальным ответам (раздел 4.4) и повторный прогон симуляций с
   откалиброванным банком.
4. Пилот подбора: 5–10 работодателей-партнёров ФСП оценивают релевантность топ-10 по своим реальным
   потребностям (P@10 по экспертной разметке) и сравнивают с привычными площадками.
"""


def versions_section() -> str:
    req = [l.strip() for l in (ROOT / "backend" / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text())
    merged: dict[str, list[str]] = {}
    for r in req:
        spec, _, marker = r.partition(";")
        name, ver = spec.strip().split("==")
        if marker:  # python_version >= "3.12" -> (Python ≥ 3.12)
            m = re.search(r'python_version\s*([<>=]+)\s*"([\d.]+)"', marker)
            if m:
                ver += f" (Python {m.group(1).replace('>=', '≥').replace('<', '<')} {m.group(2)})"
        merged.setdefault(name, []).append(ver)
    rows_b = "\n".join(f"| `{k}` | {', '.join(v)} |" for k, v in merged.items())
    rows_f = "\n".join(f"| `{k}` | {v} |" for k, v in {**pkg["dependencies"], **pkg["devDependencies"]}.items())
    mock = [l.strip() for l in (ROOT / "fsp-mock" / "requirements.txt").read_text().splitlines() if l.strip()]
    return f"""Все компоненты — открытое ПО (MIT, Apache-2.0, BSD, PostgreSQL License, OFL для шрифтов).

**Среда выполнения:** Python 3.12, Node.js 22, PostgreSQL 16, Docker-образы `python:3.12-slim`,
`node:22-alpine`, `postgres:16-alpine`, `ollama/ollama` (необязательно). Для запуска без Docker
подходят Python 3.10–3.13 и Node.js 20+, вместо PostgreSQL используется SQLite.

**Бэкенд (`backend/requirements.txt`):**

| Пакет | Версия |
|---|---|
{rows_b}

Для тестов и валидации: `pytest 9.1.1`, `matplotlib 3.11`, `playwright` (сборка PDF документации).

**Мок ФСП:** {", ".join(f"`{m}`" for m in mock)}.

**Фронтенд (`frontend/package.json`):**

| Пакет | Версия |
|---|---|
{rows_f}

**Шрифты:** Montserrat (OFL), JetBrains Mono (OFL), DejaVu Sans для PDF-профиля (свободная лицензия).

**LLM (необязательно):** любая локальная модель через OpenAI-совместимый сервер — llama.cpp (`llama-server`) или
Ollama (по умолчанию `qwen2.5:3b`, Apache-2.0). Сравнение с правилами проведено на Gemma 4 E4B-it (Q4_K_M) в
llama.cpp (п. 6.5). Без LLM система полностью работоспособна."""


def toc(md: str) -> str:
    out = []
    for line in md.splitlines():
        m = re.match(r"^(##|###) (.+)$", line)
        if m and "Содержание" not in m.group(2):
            out.append(("  " if m.group(1) == "###" else "") + f"- {m.group(2)}")
    return "**Содержание**\n\n" + "\n".join(out)


CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Montserrat, 'DejaVu Sans', sans-serif; color: #1C1D22; font-size: 10.5pt; line-height: 1.5; }
h1 { color: #2D1451; font-size: 22pt; margin: 0 0 6pt; }
h2 { color: #2D1451; font-size: 15pt; margin: 22pt 0 8pt; padding-top: 6pt; border-top: 2px solid #FF0053; page-break-after: avoid; }
h3 { color: #2D1451; font-size: 12pt; margin: 16pt 0 6pt; page-break-after: avoid; }
h4 { color: #520977; font-size: 10.5pt; margin: 12pt 0 4pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9pt; page-break-inside: auto; }
th { background: #2D1451; color: #fff; text-align: left; padding: 5pt 6pt; font-weight: 600; }
td { border-bottom: 1px solid #E4EAE9; padding: 4pt 6pt; vertical-align: top; }
tr { page-break-inside: avoid; }
code { font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace; font-size: 8.5pt; background: #F3F6F5; padding: 0 2pt; border-radius: 3px; }
pre { background: #1E1530; color: #EDE9F6; padding: 10pt; border-radius: 8px; font-size: 7.6pt; line-height: 1.35; overflow: hidden; white-space: pre; page-break-inside: avoid; }
pre code { background: none; color: inherit; font-size: inherit; padding: 0; }
img { max-width: 78%; display: block; margin: 8pt auto 2pt; page-break-inside: avoid; }
em { color: #555; }
a { color: #2D1451; }
ul, ol { padding-left: 16pt; }
li { margin: 2pt 0; }
.cover { border-left: 6px solid #FF0053; padding-left: 14pt; margin-bottom: 18pt; }
"""


def render(md: str, name: str, title: str, pdf: bool = True) -> None:
    (BUILD / f"{name}.md").write_text(md)
    import markdown
    html_body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])

    def inline_img(m):
        path = (BUILD / m.group(1)).resolve()
        if path.exists():
            return f'src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"'
        return m.group(0)
    html_body = re.sub(r'src="([^"]+\.png)"', inline_img, html_body)
    fonts = ""
    fdir = ROOT / "frontend" / "node_modules" / "@fontsource"
    for fam, sub, weights in (("Montserrat", "montserrat", (400, 600, 700)), ("JetBrains Mono", "jetbrains-mono", (400,))):
        for w in weights:
            for script in ("cyrillic", "latin"):
                f = fdir / sub / "files" / f"{sub}-{script}-{w}-normal.woff2"
                if f.exists():  # шрифты бренда встраиваются в PDF, если установлены зависимости фронтенда
                    fonts += (f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(data:font/woff2;base64,"
                              f"{base64.b64encode(f.read_bytes()).decode()}) format('woff2');}}\n")
    html = (f"<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{fonts}{CSS}</style></head><body>{html_body}</body></html>")
    (BUILD / f"{name}.html").write_text(html)
    print("HTML:", BUILD / f"{name}.html")
    if not pdf:
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto((BUILD / f"{name}.html").as_uri())
        page.wait_for_timeout(500)
        page.pdf(path=str(BUILD / f"{name}.pdf"), format="A4", print_background=True,
                 margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                 display_header_footer=True, header_template="<span></span>",
                 footer_template="<div style='font-size:8px;width:100%;text-align:center;color:#888'>ФСП Скаут · "
                                 "<span class='pageNumber'></span> / <span class='totalPages'></span></div>")
        b.close()
    print("PDF:", BUILD / f"{name}.pdf")


def main():
    pdf = "--no-pdf" not in sys.argv
    md = (DOCS / "documentation.md").read_text()
    md = md.replace("[[VALIDATION]]", validation_section())
    md = md.replace("[[API_TABLE]]", (DOCS / "_api_table.md").read_text())
    md = md.replace("[[VERSIONS]]", versions_section())
    md = md.replace("[[TOC]]", toc(md))
    render(md, "documentation", "ФСП Скаут — сопроводительная документация", pdf)
    render((DOCS / "approach_brief.md").read_text(), "approach_brief", "ФСП Скаут — краткое описание подхода", pdf)


if __name__ == "__main__":
    main()
