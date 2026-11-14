"""Показатели прогона."""

from __future__ import annotations

import numpy as np

from .sim import Trace


def run_metrics(tr: Trace) -> dict:
    T = float(tr.t[-1])
    kills = len(tr.kills)
    det = [(tk, td) for tk, td in tr.detected if td is not None]
    delays = [td - tk for tk, td in det]
    jobs = len(tr.jobs)
    done = [j for j in tr.jobs if j[3] == "done"]
    # время выполнения: от первого запуска до штатного завершения
    durations = [j[1] - j[0] for j in done]
    unsched = sum(1 for p in tr.polls if not p[1])
    return {
        "jobs": jobs,
        "kills": kills,
        "detected": len(det),
        "delay_mean": float(np.mean(delays)) if delays else np.nan,
        "jobs_with_kill": sum(1 for j in tr.jobs if j[2] > 1 or j[3] == "failed"),
        "jobs_failed": sum(1 for j in tr.jobs if j[3] == "failed"),
        "job_time": float(np.mean(durations)) if durations else np.nan,
        "polls_per_min": len(tr.polls) / T * 60,
        "unscheduled_share": unsched / max(1, len(tr.polls)),
        "overprov": float(np.mean(tr.alloc - tr.used)),
        "alloc_mean": float(np.mean(tr.alloc)),
    }
