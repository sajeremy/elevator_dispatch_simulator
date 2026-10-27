"""Run several dispatch strategies on the same input and collect their metrics.

`compare` covers one input (the CLI's comparison); `compare_workloads` runs
the grid of every strategy on every workload. Run
`python -m elevator_sim.experiments` for the standard grid.

Every run goes through `run_simulation` with the same config apart from
`dispatch`, so the comparison differs only in the dispatcher. Runs are
independent, so they go to separate processes and finish in about the time
of the slowest one.
"""

import os
import time
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import typer

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.metrics import RunMetrics, compute_metrics
from elevator_sim.models import ElevatorRequest
from elevator_sim.report import format_grid
from elevator_sim.simulation import SimulationResult, run_simulation
from elevator_sim.workloads import (
    DEFAULT_OFFICE_DAY,
    evening_rush,
    idle_gap,
    interfloor,
    morning_rush,
    office_day,
)


@dataclass(frozen=True, slots=True)
class StrategyRun:
    strategy: DispatchStrategy
    result: SimulationResult
    metrics: RunMetrics
    seconds: float  # wall time of this run alone


def compare(
    requests: Iterable[ElevatorRequest],
    config: SimulationConfig,
    strategies: Sequence[DispatchStrategy] = tuple(DispatchStrategy),
    *,
    parallel: bool = True,
) -> list[StrategyRun]:
    """One run per strategy, returned in the order given."""
    return compare_workloads(
        {"": list(requests)}, config, strategies, parallel=parallel
    )[""]


def compare_workloads(
    workloads: Mapping[str, Sequence[ElevatorRequest]],
    config: SimulationConfig,
    strategies: Sequence[DispatchStrategy] = tuple(DispatchStrategy),
    *,
    parallel: bool = True,
) -> dict[str, list[StrategyRun]]:
    """Every strategy on every workload, all with the same config apart from
    `dispatch`. Keyed by workload; each list follows `strategies`."""
    jobs = [
        (name, s, list(requests), config.model_copy(update={"dispatch": s}))
        for name, requests in workloads.items()
        for s in strategies
    ]
    if parallel and len(jobs) > 1:
        with ProcessPoolExecutor(
            max_workers=min(len(jobs), os.cpu_count() or 1)
        ) as pool:
            runs = list(pool.map(_run_one, [j[2] for j in jobs], [j[3] for j in jobs]))
    else:
        runs = [_run_one(j[2], j[3]) for j in jobs]

    grid: dict[str, list[StrategyRun]] = {name: [] for name in workloads}
    for (name, s, _, _), (result, seconds) in zip(jobs, runs, strict=True):
        grid[name].append(StrategyRun(s, result, compute_metrics(result), seconds))
    return grid


def standard_workloads(
    num_floors: int = DEFAULT_OFFICE_DAY.num_floors,
) -> dict[str, list[ElevatorRequest]]:
    """The traffic patterns from `workloads`, each sized like an office-day
    peak hour (2400 ticks), plus the office day itself."""
    hour, trips = 2400, 1000
    return {
        "office day": office_day(),
        "morning rush": morning_rush(trips, num_floors, hour, seed=1),
        "evening rush": evening_rush(trips, num_floors, hour, seed=2),
        "inter-floor": interfloor(trips, num_floors, hour, seed=3),
        "idle gap": idle_gap(trips // 4, num_floors, hour // 2, gap=2 * hour, seed=4),
    }


def _run_one(
    requests: list[ElevatorRequest], config: SimulationConfig
) -> tuple[SimulationResult, float]:
    start = time.perf_counter()
    result = run_simulation(requests, config)
    return result, time.perf_counter() - start


app = typer.Typer(
    add_completion=False, help="Compare every dispatcher on every standard workload."
)


@app.command()
def main(
    elevators: int = 8,
    capacity: int = 16,
    stop_duration: int = 1,
) -> None:
    config = SimulationConfig(
        num_floors=DEFAULT_OFFICE_DAY.num_floors,
        num_elevators=elevators,
        capacity=capacity,
        stop_duration=stop_duration,
    )
    grid = compare_workloads(standard_workloads(config.num_floors), config)
    typer.echo(
        f"{config.num_floors} floors, {elevators} cars, capacity {capacity}, "
        f"stop duration {stop_duration}\n"
    )
    typer.echo(
        format_grid(
            {
                w: [(r.strategy.value, r.metrics) for r in runs]
                for w, runs in grid.items()
            }
        )
    )


if __name__ == "__main__":
    app()
