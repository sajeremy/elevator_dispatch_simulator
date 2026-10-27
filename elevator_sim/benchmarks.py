"""Offline-optimal benchmark (the Level 2 bound) on tiny workloads.

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

Run `python -m elevator_sim.benchmarks` for the summary tables.
"""

import math
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Annotated

import typer

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.dispatch.fixed import FixedDispatcher
from elevator_sim.metrics import ideal_total, summarize
from elevator_sim.models import ElevatorRequest
from elevator_sim.simulation import SimulationResult, run_simulation
from elevator_sim.workloads import random_trips

# 2^n single-car runs and k * 3^n search steps: 16 passengers is ~43M steps.
MAX_PASSENGERS = 16


@dataclass(frozen=True, slots=True)
class Optimum:
    total: int  # least possible sum of total time
    assignment: dict[str, int]  # passenger id -> car, achieving `total`
    max_wait: int  # least possible longest wait; may need another assignment


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
    totals = [0] * (1 << n)
    waits = [0] * (1 << n)
    for mask in range(1, 1 << n):
        result = run_simulation(
            [r for i, r in enumerate(requests) if mask >> i & 1], one_car
        )
        if result.completed:
            totals[mask] = sum(p.total for p in result.passengers)
            waits[mask] = max(p.wait for p in result.passengers)
        else:
            totals[mask] = waits[mask] = math.inf

    cars = min(config.num_elevators, n)
    best_total, blocks = _best_split(totals, n, cars, lambda a, b: a + b)
    best_wait, _ = _best_split(waits, n, cars, max)
    assignment = {
        requests[i].passenger_id: car
        for car, block in enumerate(blocks)
        for i in range(n)
        if block >> i & 1
    }
    optimum = Optimum(total=best_total, assignment=assignment, max_wait=best_wait)

    replay = run_simulation(requests, config, dispatcher=FixedDispatcher(assignment))
    if _total(replay) != optimum.total:
        raise RuntimeError(
            f"replayed optimum costs {_total(replay)}, expected {optimum.total}: "
            "cars no longer independent?"
        )
    return optimum


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
    level1: int
    optimum: Optimum
    totals: dict[DispatchStrategy, int] = field(default_factory=dict)
    max_waits: dict[DispatchStrategy, int] = field(default_factory=dict)


def run_case(scenario: TinyScenario, seed: int) -> CaseResult:
    requests = scenario.requests(seed)
    config = scenario.config()
    case = CaseResult(
        seed=seed,
        level1=sum(ideal_total(r, config.stop_duration) for r in requests),
        optimum=offline_optimum(requests, config),
    )
    for strategy in DispatchStrategy:
        result = run_simulation(
            requests, config.model_copy(update={"dispatch": strategy})
        )
        case.totals[strategy] = _total(result)
        case.max_waits[strategy] = max(p.wait for p in result.passengers)
        # The bounds must hold for every dispatcher; anything else is a bug.
        if not (case.level1 <= case.optimum.total <= case.totals[strategy]):
            raise RuntimeError(f"seed {seed}: {strategy} beat the offline optimum")
        if case.optimum.max_wait > case.max_waits[strategy]:
            raise RuntimeError(f"seed {seed}: {strategy} beat the max-wait optimum")
    return case


def run_suite(
    scenario: TinyScenario, seeds: Sequence[int], *, parallel: bool = True
) -> list[CaseResult]:
    if not parallel:
        return [run_case(scenario, s) for s in seeds]
    with ProcessPoolExecutor() as pool:
        return list(pool.map(run_case, [scenario] * len(seeds), seeds, chunksize=4))


def gap_closed(case: CaseResult, strategy: DispatchStrategy) -> float | None:
    """Share of round robin's excess over the optimum that `strategy` removes;
    None when round robin is already optimal."""
    rr = case.totals[DispatchStrategy.ROUND_ROBIN]
    if rr == case.optimum.total:
        return None
    return (rr - case.totals[strategy]) / (rr - case.optimum.total)


def format_suite(scenario: TinyScenario, cases: Sequence[CaseResult]) -> str:
    strategies = list(DispatchStrategy)
    rows: list[tuple[str, list[str]]] = []

    def add(label: str, per_strategy: Callable[[DispatchStrategy], str]) -> None:
        rows.append((label, [per_strategy(s) for s in strategies]))

    ratios = {
        s: summarize([c.totals[s] / c.optimum.total for c in cases]) for s in strategies
    }
    add("total / optimum, mean", lambda s: f"{ratios[s].mean:.3f}")
    add("total / optimum, p95", lambda s: f"{ratios[s].p95:.3f}")
    add("total / optimum, worst", lambda s: f"{ratios[s].max:.3f}")

    def mean_gap(s: DispatchStrategy) -> str:
        gaps = [g for c in cases if (g := gap_closed(c, s)) is not None]
        return f"{sum(gaps) / len(gaps):.0%}" if gaps else "-"

    add("gap closed, mean", mean_gap)
    add(
        "matched optimum",
        lambda s: f"{_share(cases, lambda c: c.totals[s] == c.optimum.total)}",
    )
    etd = DispatchStrategy.ETD
    add(
        "beat ETD on total",
        lambda s: (
            "-" if s == etd else _share(cases, lambda c: c.totals[s] < c.totals[etd])
        ),
    )
    extra = {
        s: summarize([c.max_waits[s] - c.optimum.max_wait for c in cases])
        for s in strategies
    }
    add("max wait over fair optimum, mean", lambda s: f"{extra[s].mean:.1f}")
    add("max wait over fair optimum, worst", lambda s: f"{extra[s].max:.0f}")

    width = max(12, *(len(s.value) + 2 for s in strategies))
    label_width = max(len(label) for label, _ in rows) + 2
    level1 = sum(c.optimum.total / c.level1 for c in cases) / len(cases)
    setup = (
        f"{scenario.num_floors} floors, {scenario.num_elevators} cars, "
        f"capacity {scenario.capacity}, {len(cases)} seeds"
    )
    lines = [
        f"{scenario.name}  ({setup})",
        f"  optimum is {level1 - 1:.0%} above the private-car bound on average",
        "",
        " " * label_width + "".join(f"{s.value:>{width}}" for s in strategies),
    ]
    lines += [
        f"{label:<{label_width}}" + "".join(f"{v:>{width}}" for v in vs)
        for label, vs in rows
    ]
    return "\n".join(lines)


def _share(cases: Sequence[CaseResult], test: Callable[[CaseResult], bool]) -> str:
    return f"{sum(map(test, cases))}/{len(cases)}"


app = typer.Typer(
    add_completion=False, help="Compare dispatchers with the offline optimum."
)


@app.command()
def main(
    seeds: Annotated[int, typer.Option(help="Random cases per scenario.")] = 100,
) -> None:
    for scenario in TINY_SCENARIOS:
        typer.echo(format_suite(scenario, run_suite(scenario, range(seeds))))
        typer.echo("")


if __name__ == "__main__":
    app()
