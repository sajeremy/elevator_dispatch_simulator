"""Elevator request input: CSV loading and the no-peek source.

`RequestSource.arrivals_at(t)` is the only way the simulation sees requests,
so the scheduler can never observe a request before its time. Replacing the
list with a stream means replacing this one class.
"""

import csv
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from elevator_sim.models import ElevatorRequest

CSV_FIELDS = ("time", "id", "source", "dest")


def load_requests_csv(path: str | Path) -> list[ElevatorRequest]:
    """Read `time,id,source,dest` rows. Errors name the offending line."""
    requests: list[ElevatorRequest] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError(f"{path}: expected header {','.join(CSV_FIELDS)}")
        for row in reader:
            try:
                requests.append(
                    ElevatorRequest(
                        time=row["time"],
                        passenger_id=row["id"],
                        source_floor=row["source"],
                        destination_floor=row["dest"],
                    )
                )
            except ValidationError as e:
                raise ValueError(f"{path}, line {reader.line_num}: {e}") from e
    return requests


class RequestSource:
    """Releases requests in time order, never ahead of the current tick.

    Input is validated against the building and stably sorted by time, so
    requests sharing a tick keep their input order.
    """

    def __init__(self, requests: Iterable[ElevatorRequest], num_floors: int) -> None:
        pending = sorted(requests, key=lambda r: r.time)  # stable
        seen: set[str] = set()
        for r in pending:
            if r.passenger_id in seen:
                raise ValueError(f"duplicate passenger id {r.passenger_id!r}")
            seen.add(r.passenger_id)
            for floor in (r.source_floor, r.destination_floor):
                if not 1 <= floor <= num_floors:
                    raise ValueError(
                        f"request {r.passenger_id!r}: floor {floor} outside 1..{num_floors}"
                    )
        self._pending = pending
        self._next = 0
        self._last_t: int | None = None

    def arrivals_at(self, t: int) -> list[ElevatorRequest]:
        """Requests with time <= t not yet released. `t` must not go backwards."""
        if self._last_t is not None and t < self._last_t:
            raise ValueError(f"time went backwards: {t} after {self._last_t}")
        self._last_t = t
        start = self._next
        while self._next < len(self._pending) and self._pending[self._next].time <= t:
            self._next += 1
        return self._pending[start : self._next]

    @property
    def released(self) -> int:
        """How many requests have been released so far."""
        return self._next

    @property
    def exhausted(self) -> bool:
        """True once every request has been released.

        Used by the simulation loop only to decide when to stop; it is never
        passed to a strategy.
        """
        return self._next == len(self._pending)


def write_requests_csv(requests: Iterable[ElevatorRequest], path: str | Path) -> None:
    """Write requests in the format `load_requests_csv` reads."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_FIELDS)
        for r in requests:
            writer.writerow((r.time, r.passenger_id, r.source_floor, r.destination_floor))
