"""Аудит библиотек PyPI: дата последнего релиза и соответствие критерию свежести.

Критерий: последний релиз не старше трёх лет на дату проверки.
Запуск:  python scripts/pypi_audit.py [--date 2026-11-10] [--out results/pypi_audit.csv]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import urllib.request

# (класс методов, пакет PyPI, что используется)
CANDIDATES = [
    ("Сбор: процессы и память гостя", "psutil", "RSS процессов, MemAvailable"),
    ("Сбор: статистика ВМ с хоста", "libvirt-python", "virDomainMemoryStats, период статистики"),
    ("Сбор: журнал systemd", "systemd-python", "чтение journald (сообщения OOM)"),
    ("Сбор: журнал systemd", "cysystemd", "чтение journald (сообщения OOM)"),
    ("Сбор: журнал systemd", "pystemd", "управление юнитами и срезами systemd"),
    ("Сбор: события файлов cgroup", "inotify-simple", "inotify на memory.events"),
    ("Сбор: события файлов cgroup", "pyinotify", "inotify (устаревшая альтернатива)"),
    ("Сбор: трассировка eBPF", "bcc", "под этим именем на PyPI посторонний пакет"),
    ("Сбор: трассировка eBPF", "pythonbpf", "eBPF из Python"),
    ("Сбор: cgroup", "cgroupspy", "чтение cgroup (только v1)"),
    ("Сбор: cgroup", "cgroups", "управление cgroup"),
    ("Сбор: cgroup", "cgroup-utils", "утилиты cgroup"),
    ("Сбор: cgroup", "libcgroup", "обёртка libcgroup"),
    ("Выборка с цензурированием", "statsmodels", "регрессия, MarkovRegression"),
    ("Выборка с цензурированием", "lifelines", "Каплан–Мейер, Кокс, AFT с цензурированием"),
    ("Выборка с цензурированием", "scikit-survival", "модели выживаемости"),
    ("Выборка с цензурированием", "xgboost", "survival:aft с интервальным цензурированием"),
    ("Выборка с цензурированием", "py4etrics", "модель Тобит"),
    ("Выборка с цензурированием", "censored-regression", "регрессия с нижними границами"),
    ("Выборка с цензурированием", "surpyval", "выживаемость, цензурирование"),
    ("Выборка с цензурированием", "pycox", "выживаемость на PyTorch"),
    ("Выборка с цензурированием", "pymc", "байесовская модель с цензурированием"),
    ("Выборка с цензурированием", "scipy", "правдоподобие Тобит-модели (optimize, stats)"),
    ("Восстановление пропусков", "scikit-learn", "IterativeImputer, KNNImputer"),
    ("Восстановление пропусков", "fancyimpute", "восстановление матриц"),
    ("Восстановление пропусков", "autoimpute", "множественное восстановление"),
    ("Переклассификация: разладка", "ruptures", "PELT, BinSeg (оффлайн)"),
    ("Переклассификация: разладка", "river", "ADWIN, Page–Hinkley (онлайн)"),
    ("Переклассификация: разладка", "changefinder", "SDAR-разладка"),
    ("Переклассификация: разладка", "bayesian-changepoint-detection", "байесовская онлайн-разладка"),
    ("Переклассификация: разладка", "sktime", "детекторы разладки и сегментации"),
    ("Переклассификация: разладка", "alibi-detect", "дрейф данных"),
    ("Переклассификация: разладка", "kats", "разладка, CUSUM"),
    ("Переклассификация: режимы", "hmmlearn", "скрытые марковские модели"),
    ("Переклассификация: аномалии", "pyod", "детекторы аномалий"),
    ("Прогноз и фильтрация", "pykalman", "фильтр Калмана"),
    ("Прогноз и фильтрация", "filterpy", "фильтр Калмана"),
    ("Запас памяти: экстремумы", "pyextremes", "POT, обобщённое распределение Парето"),
    ("Запас памяти: интервал прогноза", "mapie", "конформные интервалы"),
    ("Запас памяти: интервал прогноза", "crepes", "конформные предикторы"),
]


def fetch(name: str) -> dict | None:
    url = f"https://pypi.org/pypi/{name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "pypi-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception:
        return None


def last_release(info: dict) -> tuple[str, dt.date | None]:
    best_v, best_d = info["info"]["version"], None
    for ver, files in info.get("releases", {}).items():
        for f in files:
            if f.get("yanked"):
                continue
            d = dt.datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00")).date()
            if best_d is None or d > best_d:
                best_v, best_d = ver, d
    return best_v, best_d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", default="results/pypi_audit.csv")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.date)
    cutoff = today.replace(year=today.year - 3)
    rows = []
    for cls, name, use in CANDIDATES:
        info = fetch(name)
        if info is None:
            rows.append([cls, name, use, "", "", "", "нет на PyPI"])
            continue
        ver, d = last_release(info)
        rp = info["info"].get("requires_python") or ""
        ok = d is not None and d >= cutoff
        rows.append([cls, name, use, ver, d.isoformat() if d else "", rp, "да" if ok else "нет"])
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "класс",
                "пакет",
                "назначение",
                "версия",
                "последний релиз",
                "requires_python",
                f"релиз после {cutoff}",
            ]
        )
        w.writerows(rows)
    for r in rows:
        print(" | ".join(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
