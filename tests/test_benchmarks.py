import itertools

import pytest

from elevator_sim.benchmarks import (
    MAX_PASSENGERS,
    TinyScenario,
    format_suite,
    gap_closed,
    offline_optimum,
    run_suite,
)
from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.dispatch.fixed import FixedDispatcher
from elevator_sim.simulation import run_simulation
from elevator_sim.workloads import random_trips


def brute_force(requests, config):
    """Every assignment simulated in full: (least total, least max wait)."""
    best_total = best_wait = float("inf")
    for cars in itertools.product(range(config.num_elevators), repeat=len(requests)):
        assignment = {r.passenger_id: c for r, c in zip(requests, cars, strict=True)}
        result = run_simulation(
            requests, config, dispatcher=FixedDispatcher(assignment)
        )
        best_total = min(best_total, sum(p.total for p in result.passengers))
        best_wait = min(best_wait, max(p.wait for p in result.passengers))
    return best_total, best_wait


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("capacity", [1, 12])
def test_optimum_matches_brute_force(seed, capacity):
    requests = random_trips(6, 12, 10, seed)
    config = SimulationConfig(num_floors=12, num_elevators=3, capacity=capacity)
    optimum = offline_optimum(requests, config)
    assert (optimum.total, optimum.max_wait) == brute_force(requests, config)


def test_optimal_assignment_replays_to_the_optimal_total():
    requests = random_trips(8, 15, 20, seed=5)
    config = SimulationConfig(num_floors=15, num_elevators=2)
    optimum = offline_optimum(requests, config)
    replay = run_simulation(
        requests, config, dispatcher=FixedDispatcher(optimum.assignment)
    )
    assert sum(p.total for p in replay.passengers) == optimum.total


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


def test_suite_bounds_and_summary():
    scenario = TinyScenario("test", passengers=6, num_floors=12, duration=10)
    cases = run_suite(scenario, range(4), parallel=False)  # run_case checks the bounds
    for case in cases:
        assert case.level1 <= case.optimum.total
        if (g := gap_closed(case, DispatchStrategy.ROUND_ROBIN)) is not None:
            assert g == 0
    text = format_suite(scenario, cases)
    assert "total / optimum, mean" in text and "4 seeds" in text


def test_etd_stays_close_to_the_offline_optimum():
    """Regression guard: on 20 fixed burst cases ETD averages 1.079x the
    optimum (round robin 1.354x, nearest car 1.211x). A change that makes ETD
    noticeably worse fails here even if it still beats round robin."""
    cases = run_suite(TinyScenario("burst", duration=15), range(20))

    def mean_ratio(s):
        return sum(c.totals[s] / c.optimum.total for c in cases) / len(cases)

    assert mean_ratio(DispatchStrategy.ETD) < 1.12
    assert mean_ratio(DispatchStrategy.ETD) < mean_ratio(DispatchStrategy.NEAREST_CAR)
    assert mean_ratio(DispatchStrategy.NEAREST_CAR) < mean_ratio(
        DispatchStrategy.ROUND_ROBIN
    )
