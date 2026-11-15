# sydost-oom-bench

Simulation bench for the article "A review of methods for accounting process failures caused by RAM shortage between monitoring points for mode reclassification and recalculation of an adaptive KVM management system" (A. O. Ferubko, O. D. Kazakov, Vestnik SPbGUPTD, Series 4).

The bench models a situation in which a user process rapidly increases its memory consumption and is killed by the guest kernel (OOM killer) between two monitoring points, while the adaptive memory management system (Ferubko, Kazakov, Vestnik RGRTU, 2026, No. 95) does not notice it. Seven accounting variants (M0–M6) are compared.

This is a model, not KVM: there is no swapping and no slowdown of processes under memory shortage. The numbers show the ratio of the methods, not the behaviour of a particular system.

Russian version: [README.ru.md](README.ru.md). Details of the variants: [docs/en/methods.md](docs/en/methods.md).

## Installation and runs

Python 3.11–3.14 is required. With [uv](https://docs.astral.sh/uv/):

```bash
uv venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e ".[test]" pillow
python -m pytest                          # 10 tests
python scripts/run_experiments.py         # 6 methods x 4 speeds x 20 runs, about 15 s
python scripts/make_figures.py            # figures 1 and 2
python scripts/pypi_audit.py --date 2026-11-10   # PyPI audit (needs internet)
```

Random seeds are fixed, so the results are reproduced exactly.

## Contents

| Path | Content |
|---|---|
| `src/sydost_oom_bench/sim.py` | model of the guest OS, processes, OOM killer and monitoring loop |
| `src/sydost_oom_bench/methods.py` | controller and accounting variants M0–M6 |
| `src/sydost_oom_bench/metrics.py` | run metrics |
| `scripts/run_experiments.py` | series of runs → `results/runs.csv`, `summary.csv`, `summary.md` |
| `scripts/sensitivity_m6.py` | sensitivity of M6 to TAU_F → `results/sensitivity_m6.md` |
| `scripts/make_figures.py` | `results/fig/fig1_timeline.*`, `fig2_summary.*` (PNG and TIFF, 600 dpi) |
| `scripts/pypi_audit.py` | last release dates of PyPI packages → `results/pypi_audit.csv` |
| `tests/test_bench.py` | pytest tests |
| `docs/ru`, `docs/en` | description of the variants and metrics |

## Variants

| Code | Variant |
|---|---|
| M0 | original algorithm: instantaneous value, regression over 5 points, interval 1–10 s by the number of redistributions |
| M1 | `oom_kill` counter: an increase of the counter switches the system to the unstable mode |
| M2 | M1 and sample recalculation: the volume of the killed process is added to the observation, the point is censored, the lower bound is held for 60 s |
| M3 | peak over the interval (`memory.peak`) instead of the instantaneous value; a peak that reaches the allocated volume is a censored observation |
| M4 | M3 with a reserve based on the 0.9 quantile of "peak minus instantaneous" and an interval limit |
| M5 | M2 and a guest event agent (free memory and growth rate thresholds) with unscheduled points |
| M6 | M2 with forgetting: exponential regression weights (TAU_W = 20 s) and a decaying lower bound (TAU_F = 30 s) instead of a 60 s hold |

## Metrics

- failures per job (with a 95 % bootstrap interval);
- failures detected and detection delay;
- jobs with a failure and unfinished jobs (five failed attempts);
- mean job time;
- monitoring points per minute;
- mean excess of allocated memory over used memory.

## Citation

See `CITATION.cff`. License: MIT (file `LICENSE`). Version: 0.0.3 (`CHANGELOG.md`).
