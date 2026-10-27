"""End-of-run statistics. Reads a SimulationResult; changes nothing."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class RunMetrics:
    passengers: int
    delivered: int
    capacity: int
    wait: Distribution | None  # request to pickup, delivered passengers only
    total: Distribution | None  # wait plus ride
    stops: Distribution | None  # intermediate stops per trip
    total_time_sum: int  # over delivered passengers; the benchmark ratio uses it
    # Capacity pressure: how often cars were full and had to move on without
    # one of their own passengers, and how much movement carried nobody.
    max_load: int
    full_ticks: int  # summed over cars
    left_behind: int  # departures that left a same-direction pickup behind
    most_left_behind: tuple[str, int] | None  # (passenger id, times), if any
    deadhead: float | None  # share of moving ticks with nobody aboard
    wrong_way_floors: (
        int  # rider-floors travelled away from a destination; 0 under LOOK
    )


def compute_metrics(result: SimulationResult) -> RunMetrics:
    delivered = [p for p in result.passengers if p.delivered]
    passed = max(
        result.passengers, key=lambda p: (p.left_behind, -p.arrival_order), default=None
    )
    stats = result.elevator_stats
    moving = sum(s.moving_ticks for s in stats)
    empty = sum(s.empty_moving_ticks for s in stats)
    return RunMetrics(
        passengers=len(result.passengers),
        delivered=len(delivered),
        capacity=result.config.capacity,
        wait=summarize([p.wait for p in delivered]),
        total=summarize([p.total for p in delivered]),
        stops=summarize([p.stops for p in delivered]),
        total_time_sum=sum(p.total for p in delivered),
        max_load=max((s.max_load for s in stats), default=0),
        full_ticks=sum(s.full_ticks for s in stats),
        left_behind=sum(s.left_behind for s in stats),
        most_left_behind=(
            (passed.request.passenger_id, passed.left_behind)
            if passed and passed.left_behind
            else None
        ),
        deadhead=empty / moving if moving else None,
        wrong_way_floors=sum(s.wrong_way_floors for s in stats),
    )
