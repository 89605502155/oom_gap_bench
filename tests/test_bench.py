import numpy as np
import pytest

from sydost_oom_bench import METHODS, Scenario, interval_rule, linear_forecast, simulate
from sydost_oom_bench.metrics import run_metrics

BY = {m.code: m for m in METHODS}


def test_interval_rule_bounds():
    assert interval_rule(0) == pytest.approx(10.0)
    assert interval_rule(5) == pytest.approx(1.0)
    assert interval_rule(9) == pytest.approx(1.0)


def test_linear_forecast_exact_on_line():
    ts = [0, 1, 2, 3, 4]
    xs = [10 + 3 * t for t in ts]
    fc, slope = linear_forecast(ts, xs, 6)
    assert fc == pytest.approx(28.0)
    assert slope == pytest.approx(3.0)


def test_used_never_exceeds_alloc():
    for m in METHODS:
        tr = simulate(Scenario(v=200, seed=3), m)
        assert np.all(tr.used <= tr.alloc + 1e-6)
        assert np.all(tr.demand >= tr.used - 1e-9)


def test_deterministic_by_seed():
    a = simulate(Scenario(v=100, seed=7), BY["M2"])
    b = simulate(Scenario(v=100, seed=7), BY["M2"])
    assert np.array_equal(a.alloc, b.alloc)
    assert a.kills == b.kills


def test_baseline_misses_all_failures():
    tr = simulate(Scenario(v=200, seed=0), BY["M0"])
    r = run_metrics(tr)
    assert r["kills"] > 0
    assert r["detected"] == 0


def test_counter_detects_every_failure():
    tr = simulate(Scenario(v=200, seed=0), BY["M1"])
    r = run_metrics(tr)
    assert r["kills"] > 0
    assert r["detected"] == r["kills"]


def test_detection_not_before_failure():
    tr = simulate(Scenario(v=400, seed=1), BY["M3"])
    for tk, td in tr.detected:
        assert td is None or td >= tk - 1e-9


@pytest.mark.parametrize("code", ["M2", "M3", "M5"])
def test_recalculation_reduces_failures(code):
    base = sum(len(simulate(Scenario(v=200, seed=s), BY["M0"]).kills) for s in range(5))
    new = sum(len(simulate(Scenario(v=200, seed=s), BY[code]).kills) for s in range(5))
    assert new < base / 2
