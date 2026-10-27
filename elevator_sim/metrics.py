"""End-of-run statistics. Reads a SimulationResult; changes nothing."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from elevator_sim.models import ElevatorRequest
from elevator_sim.simulation import SimulationResult


@dataclass(frozen=True, slots=True)
class Distribution:
    count: int
    min: float
    max: float
    mean: float
    p95: float  # nearest-rank: smallest value with >= 95% of samples at or below it


def summarize(values: Sequence[float]) -> Distribution | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered))
    return Distribution(
        count=len(ordered),
        min=ordered[0],
        max=ordered[-1],
        mean=sum(ordered) / len(ordered),
        p95=ordered[rank - 1],
    )


def ideal_total(request: ElevatorRequest, stop_duration: int) -> int:
    """Level 1 bound: a private car already waiting at the origin.

    Boarding happens on the request tick, so the passenger is charged only
    the trip itself plus the alighting stop.
    """
    return request.distance + stop_duration


@dataclass(frozen=True, slots=True)
class ElevatorMetrics:
    index: int
    passengers_served: int
    utilization: float  # share of ticks spent moving or stopped
    moving_ticks: int
    stopped_ticks: int
    idle_ticks: int


@dataclass(frozen=True, slots=True)
class RunMetrics:
    passengers: int
    delivered: int
    ticks: int
    completed: bool
    wait: Distribution | None
    total: Distribution | None
    stops: Distribution | None  # intermediate stops per trip
    total_time_sum: int
    ideal_total_sum: int  # Level 1 bound summed over delivered passengers
    longest_wait: tuple[str, int] | None  # (passenger id, wait)
    elevators: tuple[ElevatorMetrics, ...]


def compute_metrics(result: SimulationResult) -> RunMetrics:
    delivered = [p for p in result.passengers if p.delivered]
    stop = result.config.stop_duration
    worst = max(delivered, key=lambda p: (p.wait, -p.arrival_order), default=None)
    return RunMetrics(
        passengers=len(result.passengers),
        delivered=len(delivered),
        ticks=result.ticks,
        completed=result.completed,
        wait=summarize([p.wait for p in delivered]),
        total=summarize([p.total for p in delivered]),
        stops=summarize([p.stops for p in delivered]),
        total_time_sum=sum(p.total for p in delivered),
        ideal_total_sum=sum(ideal_total(p.request, stop) for p in delivered),
        longest_wait=(worst.request.passenger_id, worst.wait) if worst else None,
        elevators=tuple(
            ElevatorMetrics(
                index=i,
                passengers_served=s.passengers_served,
                utilization=s.busy_ticks / result.ticks,
                moving_ticks=s.moving_ticks,
                stopped_ticks=s.stopped_ticks,
                idle_ticks=s.idle_ticks,
            )
            for i, s in enumerate(result.elevator_stats)
        ),
    )
