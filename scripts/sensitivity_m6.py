"""Чувствительность M6 к постоянной убывания нижней границы TAU_F (без подбора и без отдельной выборки).

Запуск: python scripts/sensitivity_m6.py  ->  results/sensitivity_m6.md
Прогоны те же, что в run_experiments.py (20 зёрен), поэтому результат служит анализом
чувствительности, а не независимой проверкой. Для сравнения приведён M2.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sydost_oom_bench.methods as M  # noqa: E402
from sydost_oom_bench import METHODS, Scenario, simulate  # noqa: E402
from sydost_oom_bench.metrics import run_metrics  # noqa: E402

SPEEDS = (50, 100, 200, 400)
SEEDS = 20


def cell(method, v):
    rr = [run_metrics(simulate(Scenario(v=v, seed=s), method)) for s in range(SEEDS)]
    kpj = sum(r["kills"] for r in rr) / sum(r["jobs"] for r in rr)
    excess = float(np.mean([r["overprov"] for r in rr]))
    unfinished = sum(r["jobs_failed"] for r in rr)
    return kpj, excess, unfinished


def main() -> int:
    m2 = next(m for m in METHODS if m.code == "M2")
    m6 = next(m for m in METHODS if m.code == "M6")
    lines = [
        "| Вариант | TAU_F, с | " + " | ".join(f"v={v}: отказов на задание / избыток ОП, МиБ / не выполнено" for v in SPEEDS) + " |",
        "|---|---|" + "---|" * len(SPEEDS),
    ]
    base = [cell(m2, v) for v in SPEEDS]
    lines.append("| M2 | – | " + " | ".join(f"{k:.2f} / {e:.0f} / {u}" for k, e, u in base) + " |")
    for tau in (30.0, 60.0, 120.0):
        M.TAU_F = tau
        row = [cell(m6, v) for v in SPEEDS]
        lines.append(f"| M6 | {tau:.0f} | " + " | ".join(f"{k:.2f} / {e:.0f} / {u}" for k, e, u in row) + " |")
    M.TAU_F = 30.0  # восстановить значение, заданное до запуска
    out = ROOT / "results" / "sensitivity_m6.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
