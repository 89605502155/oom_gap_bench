"""Стенд моделирования отказов процессов между точками мониторинга ОП."""

__version__ = "0.0.1"
from .methods import METHODS, Method, interval_rule, linear_forecast
from .sim import DT, Scenario, Trace, simulate

__all__ = [
    "__version__",
    "DT",
    "Scenario",
    "Trace",
    "simulate",
    "METHODS",
    "Method",
    "interval_rule",
    "linear_forecast",
]
