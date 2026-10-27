from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.experiments import compare, compare_workloads
from elevator_sim.metrics import compute_metrics
from elevator_sim.report import format_comparison, format_grid
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE, requests


def test_runs_every_strategy_in_order_with_its_own_dispatcher():
    runs = compare(SAMPLE, SimulationConfig(), parallel=False)
    assert [r.strategy for r in runs] == list(DispatchStrategy)
    assert all(r.result.config.dispatch == r.strategy for r in runs)


def test_parallel_matches_a_direct_run():
    config = SimulationConfig()
    (run,) = compare(SAMPLE, config, [DispatchStrategy.ETD])
    runs = compare(SAMPLE, config)
    direct = compute_metrics(
        run_simulation(SAMPLE, config.model_copy(update={"dispatch": "etd"}))
    )
    assert run.metrics == direct
    assert runs[-1].metrics == direct


def test_comparison_stars_the_best_value_and_skips_ties():
    # Round robin sends b to idle e1 at floor 1 (wait 8). ETD gives it to e0,
    # which drops a at 10 and is back at 9 by t=11 (wait 6).
    reqs = requests((0, "a", 1, 10), (5, "b", 9, 1))
    config = SimulationConfig(num_floors=10, num_elevators=2)
    runs = compare(reqs, config, parallel=False)
    text = format_comparison([(r.strategy.value, r.metrics) for r in runs])
    lines = {line.split("  ")[0]: line for line in text.splitlines()}
    assert "*" not in lines["delivered"]  # tie
    by_strategy = {r.strategy: r.metrics for r in runs}
    rr, etd = (
        by_strategy[DispatchStrategy.ROUND_ROBIN],
        by_strategy[DispatchStrategy.ETD],
    )
    assert etd.wait.max < rr.wait.max
    assert lines["wait max"].rstrip().endswith("*")  # ETD, the last column
    assert "Versus round_robin" in text


def test_compare_workloads_runs_every_pair_and_formats_a_grid():
    workloads = {"one": SAMPLE, "two": requests((0, "a", 1, 10), (5, "b", 9, 1))}
    grid = compare_workloads(workloads, SimulationConfig(), parallel=False)
    assert list(grid) == ["one", "two"]
    for runs in grid.values():
        assert [r.strategy for r in runs] == list(DispatchStrategy)
    text = format_grid(
        {w: [(r.strategy.value, r.metrics) for r in runs] for w, runs in grid.items()}
    )
    assert "one (3 passengers)" in text and "two (2 passengers)" in text
