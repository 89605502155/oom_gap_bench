"""Варианты учёта отказов между точками мониторинга.

Каждый вариант — набор флагов одного контроллера.

M0  исходный алгоритм [1]: мгновенное значение занятой ОП, регрессия по пяти
    наблюдениям, свободная ОП пула делится поровну между гостем и хостом,
    интервал по числу перераспределений.
M1  счётчик oom_kill: приращение счётчика в плановой точке переводит систему
    в нестабильный режим (переклассификация), выборка не меняется.
M2  M1 + пересчёт выборки: объём завершённого процесса (из сообщения ядра)
    добавляется к наблюдению; полученное значение — нижняя граница
    потребности (цензурирование справа) и удерживается как «пол» потребности
    в течение FLOOR_HOLD секунд.
M3  наблюдение пика за интервал (memory.peak) вместо мгновенного значения;
    пик, достигший выделенного объёма, считается цензурированным и даёт «пол»
    так же, как в M2, но без агента и без сведений об объёме процесса.
M4  M3 + пересчёт запаса по квантили расхождения «пик − мгновенное значение»
    и ограничение интервала временем исчерпания свободной ОП.
M5  M2 + агент событий: внеплановая точка по порогу свободной ОП и скорости
    роста (аналог порогового уведомления PSI) с выделением запаса по оценке
    скорости роста; ограничение интервала.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .sim import DT, Scenario

R = 100.0  # минимальный запас ОП, МиБ
THRESH = 10.0  # порог перераспределения, МиБ
DT_MIN, DT_MAX = 1.0, 10.0
WINDOW = 5  # наблюдений в регрессии и циклов в правиле интервала
FLOOR_HOLD = 60.0  # время удержания нижней границы потребности, с


def interval_rule(m: int) -> float:
    """Правило [1]: интервал по числу перераспределений за пять циклов."""
    return DT_MAX - (DT_MAX - DT_MIN) * min(m, WINDOW) / WINDOW


def linear_forecast(ts, xs, t_next: float) -> tuple[float, float]:
    """Прогноз МНК по наблюдениям; возвращает (прогноз, наклон)."""
    ts = np.asarray(ts, float)
    xs = np.asarray(xs, float)
    if len(ts) < 2 or np.ptp(ts) == 0:
        return float(xs[-1]), 0.0
    slope, icpt = np.polyfit(ts - ts[-1], xs, 1)
    return float(icpt + slope * (t_next - ts[-1])), float(slope)


@dataclass(frozen=True)
class Method:
    code: str
    name: str
    counter: bool = False  # учитывать приращение счётчика oom_kill
    impute: bool = False  # пересчёт выборки по объёму завершённого процесса
    peak: bool = False  # наблюдать пик за интервал
    reserve_q: float | None = None  # квантиль для пересчёта запаса
    bound_interval: bool = False  # ограничение Δt временем исчерпания запаса
    event_driven: bool = False  # внеплановые точки по событиям агента
    low_free: float = 256.0  # порог свободной ОП для агента, МиБ
    low_rate: float = 20.0  # порог скорости роста для агента, МиБ/с

    def make_controller(self, sc: Scenario) -> Controller:
        return Controller(self, sc)


class Controller:
    def __init__(self, m: Method, sc: Scenario):
        self.m = m
        self.sc = sc
        self.alloc = sc.base + 2 * R
        self.next_poll = 0.0
        self.ts: deque = deque(maxlen=WINDOW)
        self.xs: deque = deque(maxlen=WINDOW)
        self.redistrib: deque = deque([0] * WINDOW, maxlen=WINDOW)
        self.force_unstable = 0
        self.last_counter = 0
        self.gaps: deque = deque(maxlen=50)  # пик − мгновенное значение
        self.dt = DT_MAX
        self.floor = 0.0  # нижняя граница потребности
        self.floor_until = -1.0
        self._prev_used = None
        self._t_last_event = -1e9

    # --- агент в гостевой ОС -------------------------------------------------
    def agent_event(self, t, used, alloc, killed_now):
        """Сообщение агента: ('oom', 0) при завершении процесса, ('low_mem', v̂)
        при малом запасе и быстром росте. Без агента — None."""
        if not self.m.event_driven:
            return None
        prev, self._prev_used = self._prev_used, used
        if killed_now:
            return ("oom", 0.0)
        if prev is None:
            return None
        rate = (used - prev) / DT
        if alloc - used < self.m.low_free and rate > self.m.low_rate and t - self._t_last_event > 0.5:
            self._t_last_event = t
            return ("low_mem", rate)
        return None

    # --- точка мониторинга ---------------------------------------------------
    def step(self, obs: dict) -> tuple[float, float, int]:
        m = self.m
        t, used, peak, alloc = obs["t"], obs["used"], obs["peak"], obs["alloc"]
        ev = obs["event"]
        n_new = obs["oom_counter"] - self.last_counter
        self.last_counter = obs["oom_counter"]
        detected = n_new if (m.counter or m.event_driven) else 0

        # 1. Наблюдение для выборки и признак цензурирования
        x = peak if m.peak else used
        censored = False
        if m.impute and obs["killed_sizes"]:
            x = used + max(obs["killed_sizes"])  # нижняя граница потребности
            censored = True
        if m.peak and peak >= alloc - 1.0:
            censored = True  # пик упёрся в выделенный объём
        if m.peak:
            self.gaps.append(max(0.0, peak - used))
        self.ts.append(t)
        self.xs.append(x)
        if censored:
            self.floor = max(self.floor if t < self.floor_until else 0.0, x)
            self.floor_until = t + FLOOR_HOLD

        # 2. Прогноз и новый объём
        fc, slope = linear_forecast(self.ts, self.xs, t + self.dt)
        if t < self.floor_until:
            fc = max(fc, self.floor)
        # Правило [1]: свободная ОП пула делится поровну между гостем и хостом,
        # но не меньше минимального запаса R.
        reserve = max(R, (self.sc.a_max - fc) / 2)
        if m.reserve_q is not None and len(self.gaps) >= 3:
            reserve = max(reserve, R + float(np.quantile(self.gaps, m.reserve_q)))
        a_new = fc + reserve
        if ev is not None and ev[0] == "low_mem":
            # запас на время до следующей точки и задержку баллона
            a_new = max(a_new, used + ev[1] * (DT_MIN + self.sc.act_delay) + R)
        changed = abs(a_new - alloc) > THRESH
        if not changed:
            a_new = alloc

        # 3. Классификация режима и интервал
        self.redistrib.append(1 if changed else 0)
        if detected or censored or ev is not None:
            self.force_unstable = WINDOW
        if self.force_unstable > 0:
            mcount = WINDOW
            self.force_unstable -= 1
        else:
            mcount = int(sum(self.redistrib))
        dt = interval_rule(mcount)
        if m.bound_interval:
            v_hat = max(slope, ev[1] if ev is not None and ev[0] == "low_mem" else 0.0)
            if v_hat > 0:
                dt = min(dt, max(DT_MIN, (a_new - used - R / 2) / v_hat))
        self.dt = dt
        return a_new, dt, detected


METHODS = [
    Method("M0", "Исходный алгоритм"),
    Method("M1", "Счётчик oom_kill", counter=True),
    Method("M2", "Счётчик и пересчёт выборки", counter=True, impute=True),
    Method("M3", "Пик за интервал", counter=True, peak=True),
    Method(
        "M4",
        "Пик, квантильный запас, ограничение интервала",
        counter=True,
        peak=True,
        reserve_q=0.9,
        bound_interval=True,
    ),
    Method(
        "M5",
        "Агент событий и пересчёт выборки",
        counter=True,
        impute=True,
        bound_interval=True,
        event_driven=True,
    ),
]
