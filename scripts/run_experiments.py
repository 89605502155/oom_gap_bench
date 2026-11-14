"""Серия прогонов: все методы × скорости роста × зёрна.

Запуск:  python scripts/run_experiments.py [--seeds 20] [--out results]
Выход:   results/runs.csv (по прогонам), results/summary.csv и summary.md (сводка).
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sydost_oom_bench import METHODS, Scenario, simulate  # noqa: E402
from sydost_oom_bench.metrics import run_metrics  # noqa: E402

SPEEDS = (50, 100, 200, 400)


def bootstrap_ci(x, n=2000, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return np.quantile(means, [0.025, 0.975])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for v in SPEEDS:
        for m in METHODS:
            for s in range(a.seeds):
                r = run_metrics(simulate(Scenario(v=v, seed=s), m))
                rows.append({"v": v, "method": m.code, "seed": s, **r})
    keys = list(rows[0].keys())
    with (out / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    summ = []
    for v in SPEEDS:
        for m in METHODS:
            rr = [r for r in rows if r["v"] == v and r["method"] == m.code]
            jobs = sum(r["jobs"] for r in rr)
            kills = sum(r["kills"] for r in rr)
            per_job = [r["kills"] / r["jobs"] for r in rr]
            lo, hi = bootstrap_ci(per_job)
            det = sum(r["detected"] for r in rr)
            delays = [r["delay_mean"] for r in rr if not np.isnan(r["delay_mean"])]
            jt = [r["job_time"] for r in rr if not np.isnan(r["job_time"])]
            summ.append(
                {
                    "v": v,
                    "method": m.code,
                    "jobs": jobs,
                    "kills": kills,
                    "kills_per_job": kills / jobs,
                    "kpj_ci_lo": lo,
                    "kpj_ci_hi": hi,
                    "jobs_with_kill": sum(r["jobs_with_kill"] for r in rr),
                    "jobs_failed": sum(r["jobs_failed"] for r in rr),
                    "detected": det,
                    "delay_mean": float(np.mean(delays)) if delays else np.nan,
                    "job_time": float(np.mean(jt)) if jt else np.nan,
                    "polls_per_min": float(np.mean([r["polls_per_min"] for r in rr])),
                    "overprov": float(np.mean([r["overprov"] for r in rr])),
                }
            )
    keys = list(summ[0].keys())
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(summ)

    def fmt(x, d=1):
        return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}".replace(".", ",")

    lines = [
        "| v, МиБ/с | Метод | Отказов / заданий | Отказов на задание [95 % ДИ] | Обнаружено | Задержка, с | Заданий с отказом | Не выполнено | Время задания, с | Точек в минуту | Избыток ОП, МиБ |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summ:
        lines.append(
            f"| {s['v']} | {s['method']} | {s['kills']} / {s['jobs']} | {fmt(s['kills_per_job'], 2)} [{fmt(s['kpj_ci_lo'], 2)}; {fmt(s['kpj_ci_hi'], 2)}] | "
            f"{s['detected']} | {fmt(s['delay_mean'])} | {s['jobs_with_kill']} | {s['jobs_failed']} | {fmt(s['job_time'])} | {fmt(s['polls_per_min'])} | {fmt(s['overprov'], 0)} |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
