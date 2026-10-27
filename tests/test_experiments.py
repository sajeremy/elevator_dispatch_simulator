from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.experiments import compare
from elevator_sim.metrics import compute_metrics
from elevator_sim.report import format_table, values
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE, SAMPLE_BUILDING, requests, row


def test_runs_every_strategy_in_order_with_its_own_dispatcher():
    runs = compare(SAMPLE, SAMPLE_BUILDING, parallel=False)
    assert [r.strategy for r in runs] == list(DispatchStrategy)
    assert all(r.result.config.dispatch == r.strategy for r in runs)


def test_parallel_matches_a_direct_run():
    config = SAMPLE_BUILDING
    (run,) = compare(SAMPLE, config, [DispatchStrategy.ETD])
    runs = compare(SAMPLE, config)
    direct = compute_metrics(
        run_simulation(SAMPLE, config.model_copy(update={"dispatch": "etd"}))
    )
    assert run.metrics == direct
    assert runs[-1].metrics == direct


def test_table_stars_the_dispatcher_with_the_shorter_longest_wait():
    # Round robin sends b to idle e1 at floor 1 (wait 8). ETD gives it to e0,
    # which drops a at 10 and is back at 9 sooner.
    reqs = requests((0, "a", 1, 10), (5, "b", 9, 1))
    config = SimulationConfig(num_floors=10, num_elevators=2)
    runs = compare(reqs, config, parallel=False)
    by = {r.strategy: r.metrics for r in runs}
    assert by[DispatchStrategy.ETD].wait.max < by[DispatchStrategy.ROUND_ROBIN].wait.max
    text = format_table("t", [(r.strategy.value, values(r.metrics)) for r in runs])
    assert row(text, "wait max").rstrip().endswith("*")  # ETD is the last column
    assert "*" not in row(text, "delivered")  # tie
