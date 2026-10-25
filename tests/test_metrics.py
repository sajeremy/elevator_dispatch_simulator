"""Sample input, hand-computed (round robin, LOOK, 60 floors, 4 cars, stop 1).

    passenger  car  request  pickup  dropoff  wait  travel  total  distance
    p1         e0      0       0       51       0     51     51      50
    p2         e1      0       0       37       0     37     37      36
    p3         e2     10      29       49      19     20     39      19
"""

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.metrics import compute_metrics, summarize
from elevator_sim.simulation import run_simulation

from tests.helpers import SAMPLE


@pytest.fixture(scope="module")
def metrics():
    return compute_metrics(run_simulation(SAMPLE, SimulationConfig(positions_log_path=None)))


def test_wait(metrics):
    assert (metrics.wait.min, metrics.wait.max, metrics.wait.p95) == (0, 19, 19)
    assert metrics.wait.mean == pytest.approx(19 / 3)


def test_travel_and_total(metrics):
    assert (metrics.travel.min, metrics.travel.max) == (20, 51)
    assert (metrics.total.min, metrics.total.max, metrics.total.p95) == (37, 51, 51)
    assert metrics.total.mean == pytest.approx(127 / 3)


def test_stretch(metrics):
    assert metrics.stretch.min == pytest.approx(51 / 50)
    assert metrics.stretch.max == pytest.approx(39 / 19)


def test_level1_bound(metrics):
    assert metrics.ideal_total_sum == 108  # 105 floors + 3 alighting stops
    assert metrics.total_time_sum == 127


def test_longest_wait(metrics):
    assert metrics.longest_wait == ("passenger3", 19)


def test_per_elevator(metrics):
    # 52 ticks. e0: stop, 50 moves, stop. e1: stop, 36 moves, stop, 14 idle.
    # e2: 10 idle, 19 moves, stop, 19 moves, stop, 2 idle. e3: idle throughout.
    e = metrics.elevators
    assert [(m.moving_ticks, m.stopped_ticks, m.idle_ticks) for m in e] == [
        (50, 2, 0),
        (36, 2, 14),
        (38, 2, 12),
        (0, 0, 52),
    ]
    assert [m.utilization for m in e] == pytest.approx([1.0, 38 / 52, 40 / 52, 0.0])
    assert [m.passengers_served for m in e] == [1, 1, 1, 0]


def test_p95_nearest_rank():
    assert summarize(list(range(1, 21))).p95 == 19  # ceil(0.95 * 20) = 19th value
    assert summarize(list(range(1, 101))).p95 == 95
    assert summarize([]) is None
