import itertools

import pytest

from elevator_sim.benchmarks import (
    MAX_PASSENGERS,
    TinyScenario,
    format_suite,
    offline_optimum,
    ratio,
    ratios,
    run_suite,
)
from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.dispatch.fixed import FixedDispatcher
from elevator_sim.simulation import run_simulation
from elevator_sim.workloads import random_trips
from tests.helpers import row


def brute_force(requests, config) -> int:
    """Every assignment simulated in full: the least sum of total time."""
    best = float("inf")
    for cars in itertools.product(range(config.num_elevators), repeat=len(requests)):
        assignment = {r.passenger_id: c for r, c in zip(requests, cars, strict=True)}
        result = run_simulation(
            requests, config, dispatcher=FixedDispatcher(assignment)
        )
        best = min(best, sum(p.total for p in result.passengers))
    return best


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("capacity", [1, 12])
def test_optimum_matches_brute_force(seed, capacity):
    requests = random_trips(6, 12, 10, seed)
    config = SimulationConfig(num_floors=12, num_elevators=3, capacity=capacity)
    assert offline_optimum(requests, config).total == brute_force(requests, config)


def test_optimal_assignment_replays_to_the_optimal_total():
    requests = random_trips(8, 15, 20, seed=5)
    config = SimulationConfig(num_floors=15, num_elevators=2)
    optimum = offline_optimum(requests, config)
    assert sum(p.total for p in optimum.result.passengers) == optimum.total


def test_more_cars_than_passengers():
    requests = random_trips(2, 10, 5, seed=1)
    optimum = offline_optimum(
        requests, SimulationConfig(num_floors=10, num_elevators=4)
    )
    assert len(set(optimum.assignment.values())) <= 2


def test_rejects_workloads_too_large_to_solve():
    requests = random_trips(MAX_PASSENGERS + 1, 30, 50, seed=1)
    with pytest.raises(ValueError, match="limited"):
        offline_optimum(requests, SimulationConfig(num_floors=30))


def test_suite_bounds_summary_and_ratios():
    scenario = TinyScenario("test", passengers=6, num_floors=12, duration=10)
    cases = run_suite(scenario, range(4), parallel=False)  # run_case checks the bounds
    for c in cases:
        assert c.optimum_metrics.total_time_sum == c.optimum
        assert all(c.optimum <= m.total_time_sum for m in c.metrics.values())
    text = format_suite(scenario, cases)
    lines = text.splitlines()
    assert lines[0] == "test; 12 floors, 3 cars, capacity 12; mean of 4 seeds"
    assert lines[2].split() == ["round_robin", "nearest_car", "etd", "optimum"]
    assert "  total / optimum, mean " in text and "  total / optimum, worst " in text
    assert (
        row(text, "total / optimum, worst").split()[-1] == "1.00"
    )  # the optimum column
    assert "gap closed" not in text and "private-car" not in text
    r = ratios(cases)
    assert set(r) == {s.value for s in DispatchStrategy}
    assert all(1.0 <= mean <= worst for mean, worst in r.values())


def test_etd_stays_close_to_the_offline_optimum():
    """Regression guard: on 20 fixed burst cases ETD averages 1.079x the
    optimum (round robin 1.354x, nearest car 1.211x). A change that makes ETD
    noticeably worse fails here even if it still beats round robin."""
    cases = run_suite(TinyScenario("burst", duration=15), range(20))

    def mean_ratio(s):
        return sum(ratio(c, s) for c in cases) / len(cases)

    assert mean_ratio(DispatchStrategy.ETD) < 1.12
    assert mean_ratio(DispatchStrategy.ETD) < mean_ratio(DispatchStrategy.NEAREST_CAR)
    assert mean_ratio(DispatchStrategy.NEAREST_CAR) < mean_ratio(
        DispatchStrategy.ROUND_ROBIN
    )
