"""График к п. 6.5: правила, LLM и гибрид на отложенном наборе текстов (по результатам llm_compare.py).

Запуск: python validation/plot_text_methods.py [имя файла llm_compare_*.json]; без аргумента — первый прогон с моделью.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from common import OUT, PALETTE, setup_matplotlib

# проверено validate_palette (светлый фон): яркость, насыщенность, различимость при дальтонизме, контраст
COLORS = {"rules": PALETTE["lavender"], "llm": PALETTE["signal"], "hybrid": "#5B3A8E"}
NAMES = {"rules": "Правила", "llm": "LLM", "hybrid": "Гибрид (как в продукте)"}
ROWS = [
    ("Резюме: все поля без ошибок", lambda d, m: d["resume"][m]["all_fields_ok"]),
    ("Резюме: ФИО", lambda d, m: d["resume"][m]["fields"]["full_name"]),
    ("Резюме: город", lambda d, m: d["resume"][m]["fields"]["city"]),
    ("Резюме: стаж (±0,5 года)", lambda d, m: d["resume"][m]["fields"]["years_experience"]),
    ("Резюме: навыки, F1", lambda d, m: d["resume"][m]["skills"]["f1"]),
    ("Потребность: грейд", lambda d, m: d["needs"][m]["grades_exact"]),
    ("Потребность: формат работы", lambda d, m: d["needs"][m]["formats"]),
    ("Потребность: навыки, F1", lambda d, m: d["needs"][m]["skills"]["f1"]),
    ("Ответ: отметки по рубрике верны", lambda d, m: d["rubric"][m]["criteria_accuracy"]),
]


def main():
    files = [f for f in sorted(OUT.glob("llm_compare_*.json")) if f.name != "llm_compare_rules.json"]
    if len(sys.argv) > 1:
        files = [OUT / sys.argv[1]]
    if not files:
        print("Нет результатов прогона с моделью: сначала python validation/llm_compare.py")
        return
    d = json.loads(files[0].read_text(encoding="utf-8"))
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    y = np.arange(len(ROWS))
    h = 0.26
    for k, m in enumerate(("rules", "llm", "hybrid")):
        vals = [get(d, m) for _, get in ROWS]
        ax.barh(y + (k - 1) * h, vals, height=h, color=COLORS[m], label=NAMES[m], edgecolor="white", linewidth=1.2)
    ax.set_yticks(y, [r[0] for r in ROWS])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.grid(axis="x", color=PALETTE["mist"], lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("доля верных (для навыков — F1)", fontsize=9)
    ax.legend(loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=3, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_text_methods.png")
    plt.close(fig)
    print(OUT / "fig_text_methods.png")


if __name__ == "__main__":
    main()
