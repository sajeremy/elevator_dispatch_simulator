"""Offline-optimal benchmark on tiny workloads.

The optimum knows every request in advance and tries every assignment of
passengers to cars, under the same physics and LOOK movement as the
dispatchers. No-peek applies to the algorithms under test, not to this.

Cars never interact (each one's route depends only on its own passengers),
so an assignment's cost is the sum of each car's cost serving its subset
alone. That makes the search exact without simulating every assignment:

1. Simulate each of the 2^n passenger subsets on a single car.
2. Combine them over the ways to split the passengers among k cars, by
   dynamic programming over subsets (about k * 3^n steps).

All cars start on the same floor, so which car gets which subset does not
matter. Every optimum is replayed through a full multi-car run to confirm
it, which would catch a change that made cars interact.

Run `python -m elevator_sim benchmark` for the tables and chart: the shared
table, averaged over seeds, with the optimum as a reference column and two
extra rows, total time relative to the optimum (mean and worst case).
"""

import math
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.dispatch.fixed import FixedDispatcher
from elevator_sim.metrics import RunMetrics, compute_metrics
from elevator_sim.models import ElevatorRequest
from elevator_sim.report import (
    OBJECTIVE_TIME,
    ROWS,
    Row,
    format_table,
    mean_values,
    values,
)
from elevator_sim.simulation import SimulationResult, run_simulation
from elevator_sim.workloads import random_trips

# 2^n single-car runs and k * 3^n search steps: 16 passengers is ~43M steps.
MAX_PASSENGERS = 16


@dataclass(frozen=True, slots=True)
class Optimum:
    total: int  # least possible sum of total time
    assignment: dict[str, int]  # passenger id -> car, achieving `total`
    result: SimulationResult  # the replay that confirmed `total`


def offline_optimum(
    requests: Sequence[ElevatorRequest], config: SimulationConfig
) -> Optimum:
    requests = sorted(requests, key=lambda r: r.time)  # stable, like RequestSource
    n = len(requests)
    if n > MAX_PASSENGERS:
        raise ValueError(
            f"offline optimum is limited to {MAX_PASSENGERS} passengers, got {n}"
        )

    # The single-car runs don't need a real dispatcher.
    one_car = config.model_copy(
        update={"num_elevators": 1, "dispatch": DispatchStrategy.ROUND_ROBIN}
    )
    totals: list[float] = [0] * (1 << n)
    for mask in range(1, 1 << n):
        result = run_simulation(
            [r for i, r in enumerate(requests) if mask >> i & 1], one_car
        )
        totals[mask] = _total(result) if result.completed else math.inf

    cars = min(config.num_elevators, n)
    best_total, blocks = _best_split(totals, n, cars, lambda a, b: a + b)
    assignment = {
        requests[i].passenger_id: car
        for car, block in enumerate(blocks)
        for i in range(n)
        if block >> i & 1
    }

    replay = run_simulation(requests, config, dispatcher=FixedDispatcher(assignment))
    if _total(replay) != best_total:
        raise RuntimeError(
            f"replayed optimum costs {_total(replay)}, expected {best_total}: "
            "cars no longer independent?"
        )
    return Optimum(total=best_total, assignment=assignment, result=replay)


def _best_split(
    cost: list[float], n: int, cars: int, combine: Callable[[float, float], float]
) -> tuple[float, list[int]]:
    """Least combined cost of splitting all n passengers among up to `cars`
    cars, and the subsets (bit masks) that achieve it."""
    full = (1 << n) - 1
    best = list(cost)  # best[mask] using one car
    picks: list[
        list[int]
    ] = []  # picks[j][mask]: subset given to one car when using j + 2 cars
    for _ in range(1, cars):
        previous, best = best, list(best)  # start from "one fewer car is enough"
        pick = [0] * (full + 1)
        for mask in range(1, full + 1):
            low = mask & -mask  # the subset holding this passenger goes to the new car
            rest = mask ^ low
            sub = rest
            while True:
                block = sub | low
                value = combine(cost[block], previous[mask ^ block])
                if value < best[mask]:
                    best[mask], pick[mask] = value, block
                if sub == 0:
                    break
                sub = (sub - 1) & rest
        picks.append(pick)

    blocks = []
    mask, level = full, cars - 1
    while mask:
        if level == 0:
            blocks.append(mask)
            break
        block = picks[level - 1][mask]
        if block:
            blocks.append(block)
            mask ^= block
        level -= 1
    return best[full], blocks


def _total(result: SimulationResult) -> int:
    return sum(p.total for p in result.passengers)


@dataclass(frozen=True, slots=True)
class TinyScenario:
    name: str
    passengers: int = 10
    num_floors: int = 20
    num_elevators: int = 3
    capacity: int = 12
    duration: int = 100  # arrival times uniform in [0, duration)

    def config(self) -> SimulationConfig:
        return SimulationConfig(
            num_floors=self.num_floors,
            num_elevators=self.num_elevators,
            capacity=self.capacity,
        )

    def requests(self, seed: int) -> list[ElevatorRequest]:
        return random_trips(self.passengers, self.num_floors, self.duration, seed)


TINY_SCENARIOS = (
    TinyScenario("light: 10 trips over 200 ticks", duration=200),
    TinyScenario("burst: 10 trips over 15 ticks", duration=15),
    TinyScenario("burst, capacity 2", duration=15, capacity=2),
)


@dataclass(frozen=True, slots=True)
class CaseResult:
    seed: int
    optimum: int  # least possible sum of total time
    metrics: dict[DispatchStrategy, RunMetrics]  # one per dispatcher
    optimum_metrics: RunMetrics  # the optimal assignment, replayed


def run_case(scenario: TinyScenario, seed: int) -> CaseResult:
    requests = scenario.requests(seed)
    config = scenario.config()
    optimum = offline_optimum(requests, config)
    metrics = {}
    for strategy in DispatchStrategy:
        result = run_simulation(
            requests, config.model_copy(update={"dispatch": strategy})
        )
        metrics[strategy] = compute_metrics(result)
        # The bound must hold for every dispatcher; anything else is a bug.
        if metrics[strategy].total_time_sum < optimum.total:
            raise RuntimeError(f"seed {seed}: {strategy} beat the offline optimum")
    return CaseResult(
        seed=seed,
        optimum=optimum.total,
        metrics=metrics,
        optimum_metrics=compute_metrics(optimum.result),
    )


def run_suite(
    scenario: TinyScenario, seeds: Sequence[int], *, parallel: bool = True
) -> list[CaseResult]:
    if not parallel:
        return [run_case(scenario, s) for s in seeds]
    with ProcessPoolExecutor() as pool:
        return list(pool.map(run_case, [scenario] * len(seeds), seeds, chunksize=4))


def ratio(case: CaseResult, strategy: DispatchStrategy) -> float:
    """Total time of the dispatcher's run over the least possible."""
    return case.metrics[strategy].total_time_sum / case.optimum


def ratios(cases: Sequence[CaseResult]) -> dict[str, tuple[float, float]]:
    """Per dispatcher name, the (mean, worst) ratio to the optimum over the cases."""
    out = {}
    for strategy in DispatchStrategy:
        rs = [ratio(c, strategy) for c in cases]
        out[strategy.value] = (sum(rs) / len(rs), max(rs))
    return out


RATIO_MEAN, RATIO_WORST = "total / optimum, mean", "total / optimum, worst"
RATIO_ROWS = (
    Row(OBJECTIVE_TIME, RATIO_MEAN, ".2f", True),
    Row(OBJECTIVE_TIME, RATIO_WORST, ".2f", True),
)
# Counts become means over seeds, so they take a decimal.
AVERAGED_ROWS = tuple(replace(r, fmt=".1f") if r.fmt == "d" else r for r in ROWS)


def title(scenario: TinyScenario, seeds: int) -> str:
    return (
        f"{scenario.name}; {scenario.num_floors} floors, "
        f"{scenario.num_elevators} cars, capacity {scenario.capacity}; "
        f"mean of {seeds} seeds"
    )


def format_suite(scenario: TinyScenario, cases: Sequence[CaseResult]) -> str:
    """The shared table averaged over the cases, one column per dispatcher,
    the optimum as the reference column, plus the two ratio rows."""
    by_strategy = ratios(cases)
    columns = []
    for strategy in DispatchStrategy:
        mean, worst = by_strategy[strategy.value]
        cells = mean_values([values(c.metrics[strategy]) for c in cases])
        columns.append((strategy.value, cells | {RATIO_MEAN: mean, RATIO_WORST: worst}))
    optimum = mean_values([values(c.optimum_metrics) for c in cases])
    reference = ("optimum", optimum | {RATIO_MEAN: 1.0, RATIO_WORST: 1.0})
    return format_table(
        title(scenario, len(cases)),
        columns,
        rows=(*AVERAGED_ROWS, *RATIO_ROWS),
        reference=reference,
    )
