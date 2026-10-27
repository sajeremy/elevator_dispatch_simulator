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
    max_load: int
    full_ticks: int
    empty_moving_ticks: int
    left_behind: int


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
    # Capacity pressure: how often cars were full and had to move on without
    # one of their own passengers, and how much movement carried nobody.
    max_load: int
    full_ticks: int  # summed over cars
    left_behind: int  # departures that left a same-direction pickup behind
    most_left_behind: tuple[str, int] | None  # (passenger id, times), if any
    deadhead: float | None  # share of moving ticks with nobody aboard


def compute_metrics(result: SimulationResult) -> RunMetrics:
    delivered = [p for p in result.passengers if p.delivered]
    stop = result.config.stop_duration
    worst = max(delivered, key=lambda p: (p.wait, -p.arrival_order), default=None)
    passed = max(
        result.passengers, key=lambda p: (p.left_behind, -p.arrival_order), default=None
    )
    moving = sum(s.moving_ticks for s in result.elevator_stats)
    empty = sum(s.empty_moving_ticks for s in result.elevator_stats)
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
                max_load=s.max_load,
                full_ticks=s.full_ticks,
                empty_moving_ticks=s.empty_moving_ticks,
                left_behind=s.left_behind,
            )
            for i, s in enumerate(result.elevator_stats)
        ),
        max_load=max((s.max_load for s in result.elevator_stats), default=0),
        full_ticks=sum(s.full_ticks for s in result.elevator_stats),
        left_behind=sum(s.left_behind for s in result.elevator_stats),
        most_left_behind=(
            (passed.request.passenger_id, passed.left_behind)
            if passed and passed.left_behind
            else None
        ),
        deadhead=empty / moving if moving else None,
    )
