"""Run logs: the per-tick positions CSV and the per-passenger CSV."""

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from elevator_sim.models import Passenger

PASSENGER_FIELDS = (
    "id",
    "elevator",
    "request_time",
    "source",
    "dest",
    "pickup_time",
    "dropoff_time",
    "wait",
    "travel",
    "total",
    "stops",
    "left_behind",
)


def write_passengers_csv(passengers: Iterable[Passenger], path: str | Path) -> None:
    """One row per passenger in arrival order. Times a passenger never reached
    (not picked up, or not dropped off) are left blank."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(PASSENGER_FIELDS)
        for p in passengers:
            r = p.request
            picked, dropped = p.pickup_time is not None, p.delivered
            writer.writerow(
                (
                    r.passenger_id,
                    p.elevator,
                    r.time,
                    r.source_floor,
                    r.destination_floor,
                    p.pickup_time if picked else "",
                    p.dropoff_time if dropped else "",
                    p.wait if picked else "",
                    p.travel if dropped else "",
                    p.total if dropped else "",
                    p.stops,
                    p.left_behind,
                )
            )


class PositionRecorder:
    """Collects one row of elevator floors per tick. Observes only."""

    def __init__(self, num_elevators: int) -> None:
        self.header = ("time", *(f"e{i}" for i in range(num_elevators)))
        self.rows: list[tuple[int, ...]] = []

    def record(self, t: int, floors: Sequence[int]) -> None:
        self.rows.append((t, *floors))

    def write_csv(self, path: str | Path) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.header)
            writer.writerows(self.rows)
