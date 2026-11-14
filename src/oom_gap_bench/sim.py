"""Имитационная модель: гостевая ОС, процесс пользователя, контроллер с опросом.

Модель воспроизводит сценарий, в котором процесс пользователя быстро наращивает
потребление оперативной памяти (ОП) и завершается ядром гостевой ОС (OOM killer)
между двумя точками мониторинга.

Время дискретно с шагом DT. Объёмы в МиБ, время в секундах.

Гостевая ОС
    Потребность D(t) = фон b(t) + сумма объёмов активных процессов пользователя.
    Если D(t) превышает выделенный объём A(t), ядро завершает наибольший процесс:
    его объём освобождается, счётчик oom_kill увеличивается на 1, а событие
    записывается в журнал (для эталона).

Контроллер (алгоритм статьи [1], упрощённо)
    В точке мониторинга t_k измеряет занятую ОП, прогнозирует её линейной
    регрессией по последним пяти наблюдениям и выставляет A = прогноз + запас.
    Перераспределение засчитывается, если |A_new - A_old| > порога.
    Интервал до следующей точки определяется числом перераспределений m за
    пять последних циклов: Δt = 10 - 1,8·m (от 10 с при m = 0 до 1 с при m = 5).

Варианты учёта отказов задаются классом Method (methods.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DT = 0.1  # шаг модели, с


@dataclass
class Scenario:
    """Параметры одного прогона."""

    v: float = 200.0  # скорость роста потребления процесса, МиБ/с
    job_size: float = 600.0  # объём, до которого растёт процесс, МиБ
    job_hold: float = 10.0  # время работы после достижения объёма, с
    retry_delay: float = 8.0  # пауза пользователя перед повторным запуском, с
    max_tries: int = 5  # предельное число попыток на задание
    n_jobs: int = 3  # число заданий в прогоне
    job_gap: tuple[float, float] = (40.0, 80.0)  # пауза между заданиями, с
    warmup: float = 30.0  # стабильная работа до первого задания, с
    tail: float = 40.0  # работа после последнего задания, с
    base: float = 350.0  # фоновое потребление гостевой ОС, МиБ
    base_noise: float = 4.0  # СКО шума фона за шаг, МиБ
    a_max: float = 1100.0  # предельный объём ОП гостя (пул минус хост), МиБ
    a_min: float = 300.0  # минимальный объём ОП гостя, МиБ
    act_delay: float = 0.5  # задержка применения нового объёма (баллон), с
    seed: int = 0


@dataclass
class Trace:
    """Результаты прогона: временные ряды и журнал событий."""

    t: np.ndarray
    demand: np.ndarray  # потребность D(t)
    used: np.ndarray  # занятая ОП min(D, A) после действия ядра
    alloc: np.ndarray  # выделенный объём A(t)
    polls: list = field(default_factory=list)  # (t, плановая?, Δt после)
    kills: list = field(default_factory=list)  # (t, объём процесса)
    detected: list = field(default_factory=list)  # (t отказа, t обнаружения | None)
    jobs: list = field(default_factory=list)  # (t запуска, t завершения | None, попыток)
    events: list = field(default_factory=list)  # (t, тип) сообщения агента


class _Job:
    __slots__ = ("start", "size", "state", "t_state", "tries", "first_start", "done_t")

    def __init__(self, t: float):
        self.first_start = t
        self.start = t
        self.size = 0.0
        self.state = "grow"  # grow | hold | wait | done | failed
        self.t_state = t
        self.tries = 1
        self.done_t = None


def simulate(sc: Scenario, method) -> Trace:
    """Один прогон модели с заданным методом учёта отказов."""
    rng = np.random.default_rng(sc.seed)
    # Моменты первого запуска заданий
    starts = []
    t0 = sc.warmup + rng.uniform(0, 10)
    for _ in range(sc.n_jobs):
        starts.append(t0)
        t0 += rng.uniform(*sc.job_gap)
    horizon = starts[-1] + sc.job_gap[1] + sc.tail
    n = int(round(horizon / DT))
    t_arr = np.arange(n) * DT
    demand = np.empty(n)
    used = np.empty(n)
    alloc = np.empty(n)

    base = sc.base
    jobs: list[_Job] = []
    pending = list(starts)
    oom_counter = 0
    peak_since_poll = 0.0
    killed_since_poll: list[float] = []
    pending_alloc: tuple[float, float] | None = None  # (момент применения, объём)
    tr = Trace(t_arr, demand, used, alloc)

    ctl = method.make_controller(sc)
    a = ctl.alloc
    next_poll = ctl.next_poll

    for i in range(n):
        t = i * DT
        # Запуск заданий
        while pending and t >= pending[0]:
            jobs.append(_Job(pending.pop(0)))
        # Фон: случайное блуждание с возвратом к среднему
        base += -0.02 * (base - sc.base) + rng.normal(0, sc.base_noise) * np.sqrt(DT)
        # Применение ранее заданного объёма (с задержкой баллона)
        if pending_alloc is not None and t >= pending_alloc[0] - 1e-9:
            a, pending_alloc = pending_alloc[1], None
        # Процессы пользователя
        for j in jobs:
            if j.state == "grow":
                j.size = min(sc.job_size, j.size + sc.v * DT)
                if j.size >= sc.job_size:
                    j.state, j.t_state = "hold", t
            elif j.state == "hold" and t - j.t_state >= sc.job_hold:
                j.state, j.size, j.done_t = "done", 0.0, t
            elif j.state == "wait" and t - j.t_state >= sc.retry_delay:
                j.state, j.t_state, j.start, j.size = "grow", t, t, 0.0
                j.tries += 1
        d = base + sum(j.size for j in jobs if j.state in ("grow", "hold"))
        # OOM killer: завершает наибольший процесс, пока потребность > A
        killed_now = []
        while d > a:
            live = [j for j in jobs if j.state in ("grow", "hold") and j.size > 0]
            if not live:
                break
            victim = max(live, key=lambda j: j.size)
            killed_now.append(victim.size)
            killed_since_poll.append(victim.size)
            d -= victim.size
            tr.kills.append((t, victim.size))
            oom_counter += 1
            victim.size = 0.0
            if victim.tries >= sc.max_tries:
                victim.state = "failed"
            else:
                victim.state, victim.t_state = "wait", t
        demand[i] = d + sum(killed_now)  # потребность до вмешательства ядра
        used[i] = d
        peak_since_poll = max(peak_since_poll, min(demand[i], a))

        # Агент в гостевой ОС (для методов с событиями)
        ev = ctl.agent_event(t, d, a, killed_now)
        if ev is not None:
            tr.events.append((t, ev))

        # Точка мониторинга: плановая или внеплановая по событию
        unscheduled = ev is not None
        if t >= next_poll - 1e-9 or unscheduled:
            obs = {
                "t": t,
                "used": d,
                "peak": peak_since_poll,
                "oom_counter": oom_counter,
                "alloc": a,
                "event": ev,
                "killed_sizes": list(killed_since_poll),
            }
            a_new, dt_next, n_detected = ctl.step(obs)
            for _ in range(n_detected):
                tr.detected.append(t)
            a_new = float(np.clip(a_new, sc.a_min, sc.a_max))
            if a_new != a:
                # уменьшение и увеличение объёма выполняются с задержкой
                pending_alloc = (t + sc.act_delay, a_new)
            next_poll = t + dt_next
            tr.polls.append((t, not unscheduled, dt_next))
            peak_since_poll = d
            killed_since_poll = []
        alloc[i] = a

    for j in jobs:
        tr.jobs.append((j.first_start, j.done_t, j.tries, j.state))
    # Связать обнаружения с моментами отказов
    tr.detected = _match_detections(tr.kills, tr.detected)
    return tr


def _match_detections(kills, det_times):
    """Сопоставить отказы и обнаружения по порядку (контроллер учитывает
    отказы по счётчику, поэтому k-е обнаружение относится к k-му отказу)."""
    out = []
    for k, (tk, _) in enumerate(kills):
        out.append((tk, det_times[k] if k < len(det_times) else None))
    return out
