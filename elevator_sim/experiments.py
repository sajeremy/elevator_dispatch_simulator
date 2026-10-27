"""Run several dispatch strategies on the same input and collect their metrics.

Every run goes through `run_simulation` with the same config apart from
`dispatch`, so the comparison differs only in the dispatcher. Runs are
independent, so they go to separate processes and finish in about the time
of the slowest one.
"""

import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.metrics import RunMetrics, compute_metrics
from elevator_sim.models import ElevatorRequest
from elevator_sim.simulation import SimulationResult, run_simulation


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
    requests = list(requests)
    configs = [config.model_copy(update={"dispatch": s}) for s in strategies]
    if parallel and len(configs) > 1:
        with ProcessPoolExecutor(max_workers=len(configs)) as pool:
            runs = list(pool.map(_run_one, [requests] * len(configs), configs))
    else:
        runs = [_run_one(requests, c) for c in configs]
    return [
        StrategyRun(s, result, compute_metrics(result), seconds)
        for s, (result, seconds) in zip(strategies, runs, strict=True)
    ]


def _run_one(
    requests: list[ElevatorRequest], config: SimulationConfig
) -> tuple[SimulationResult, float]:
    start = time.perf_counter()
    result = run_simulation(requests, config)
    return result, time.perf_counter() - start
