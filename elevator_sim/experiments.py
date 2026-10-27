"""Run every dispatch strategy on the same input and collect the metrics.

Each run goes through `run_simulation` with the same config apart from
`dispatch`, so the comparison differs only in the dispatcher. The runs are
independent, so they go to separate processes and the comparison takes
about as long as its slowest run.
"""

import os
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
        with ProcessPoolExecutor(
            max_workers=min(len(configs), os.cpu_count() or 1)
        ) as pool:
            results = list(pool.map(run_simulation, [requests] * len(configs), configs))
    else:
        results = [run_simulation(requests, c) for c in configs]
    return [
        StrategyRun(s, result, compute_metrics(result))
        for s, result in zip(strategies, results, strict=True)
    ]
