"""Рисунки к статье.

Рис. 1  временные диаграммы одного прогона (v = 200 МиБ/с) для M0, M2, M5:
        1 — занятая ОП гостя, 2 — выделенный объём, × — отказ процесса,
        нижний ряд штрихов — плановые точки, верхний — внеплановые;
Рис. 2  сводка серии: отказов на задание и точек мониторинга в минуту.

Запуск (после run_experiments.py):  python scripts/make_figures.py [--out results/fig]
Формат: PNG и TIFF 600 dpi, ширина 165 мм. Шрифт Times New Roman.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sydost_oom_bench import METHODS, Scenario, simulate  # noqa: E402

MM = 1 / 25.4
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 9,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.0,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "axes.formatter.use_locale": False,
    }
)


def comma(ax):
    """Десятичная запятая на осях."""
    from matplotlib.ticker import FuncFormatter

    f = FuncFormatter(lambda x, _: (f"{x:g}").replace(".", ","))
    ax.xaxis.set_major_formatter(f)
    ax.yaxis.set_major_formatter(f)


def save(fig, out: pathlib.Path, name: str):
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", dpi=600)
    fig.savefig(out / f"{name}.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)


def fig_timeline(out: pathlib.Path, seed: int = 2, v: float = 200.0):
    by = {m.code: m for m in METHODS}
    codes = ("M0", "M2", "M5")
    fig, axes = plt.subplots(3, 1, figsize=(165 * MM, 120 * MM), sharex=True)
    sc = Scenario(v=v, seed=seed)
    t0, t1 = None, None
    for ax, code, letter in zip(axes, codes, "абв", strict=False):
        tr = simulate(sc, by[code])
        if t0 is None:
            first = tr.jobs[0][0]
            t0, t1 = first - 8, first + 62
        sel = (tr.t >= t0) & (tr.t <= t1)
        t = tr.t[sel]
        ax.plot(t, tr.used[sel] / 1024, color="black", lw=1.0)
        ax.plot(t, tr.alloc[sel] / 1024, color="black", lw=1.6, drawstyle="steps-post", alpha=0.55)
        pt = [p[0] for p in tr.polls if t0 <= p[0] <= t1 and p[1]]
        pu = [p[0] for p in tr.polls if t0 <= p[0] <= t1 and not p[1]]
        ax.plot(pt, [0.08] * len(pt), "|", color="black", ms=6, mew=0.8)
        ax.plot(pu, [0.16] * len(pu), "|", color="0.45", ms=6, mew=0.8)
        for tk, _ in tr.kills:
            if t0 <= tk <= t1:
                ax.plot([tk], [1.12], marker="x", color="black", ms=5, mew=1.0)
        ax.set_ylim(0, 1.2)
        ax.set_xlim(t0, t1)
        ax.set_ylabel("ОП, ГиБ")
        ax.text(0.005, 0.97, f"{letter})", transform=ax.transAxes, va="top", ha="left")
        comma(ax)
        # цифровые обозначения кривых
        i = int(np.searchsorted(t, t0 + 3))
        ax.annotate(
            "1", (t[i], tr.used[sel][i] / 1024), xytext=(0, 4), textcoords="offset points", fontsize=8
        )
        k = int(np.searchsorted(t, t0 + 1))
        ax.annotate(
            "2", (t[k], tr.alloc[sel][k] / 1024), xytext=(0, 4), textcoords="offset points", fontsize=8
        )
    axes[-1].set_xlabel("t, с")
    fig.tight_layout(h_pad=0.4)
    save(fig, out, "fig1_timeline")


def fig_summary(out: pathlib.Path, summary_csv: pathlib.Path):
    rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    speeds = sorted({int(r["v"]) for r in rows})
    codes = [m.code for m in METHODS]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(165 * MM, 62 * MM))
    w = 0.13
    hatches = ["", "////", "....", "xxxx", "\\\\\\\\", ""]
    shades = ["0.15", "0.85", "0.85", "0.85", "0.85", "0.55"]
    x = np.arange(len(speeds))
    for k, c in enumerate(codes):
        rr = {int(r["v"]): r for r in rows if r["method"] == c}
        y = [float(rr[v]["kills_per_job"]) for v in speeds]
        lo = [float(rr[v]["kills_per_job"]) - float(rr[v]["kpj_ci_lo"]) for v in speeds]
        hi = [float(rr[v]["kpj_ci_hi"]) - float(rr[v]["kills_per_job"]) for v in speeds]
        p = [float(rr[v]["polls_per_min"]) for v in speeds]
        xx = x + (k - 2.5) * w
        a1.bar(xx, y, w, color=shades[k], edgecolor="black", lw=0.4, hatch=hatches[k], label=c)
        a1.errorbar(xx, y, yerr=[lo, hi], fmt="none", ecolor="black", elinewidth=0.5, capsize=1.2)
        a2.bar(xx, p, w, color=shades[k], edgecolor="black", lw=0.4, hatch=hatches[k], label=c)
    for ax, lab, letter in ((a1, "Отказов на задание", "а"), (a2, "Точек мониторинга в минуту", "б")):
        ax.set_xticks(x, [str(v) for v in speeds])
        ax.set_xlabel("v, МиБ/с")
        ax.set_ylabel(lab)
        ax.text(0.01, 0.98, f"{letter})", transform=ax.transAxes, va="top")
    a2.legend(ncol=3, fontsize=7.5, frameon=False, loc="upper right", handlelength=1.6, columnspacing=0.8)
    a1.set_ylim(0, 5.6)
    a2.set_ylim(0, 38)
    fig.tight_layout(w_pad=1.0)
    save(fig, out, "fig2_summary")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "fig"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    fig_timeline(out)
    fig_summary(out, ROOT / "results" / "summary.csv")
    print("рисунки:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
