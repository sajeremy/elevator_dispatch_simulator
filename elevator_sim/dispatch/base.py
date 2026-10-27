from collections.abc import Sequence
from typing import Protocol

from elevator_sim.models import ElevatorRequest, ElevatorView


class Dispatcher(Protocol):
    """Chooses the car for a new request. The choice is permanent."""

    def assign(
        self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int
    ) -> int:
        """Return the index of the elevator that will serve `request`."""
        ...


class RotatingTies:
    """Picks the car with the lowest score. Among equal scores, the first car
    after the one picked last time, so ties rotate instead of piling onto
    car 0: idle cars waiting together at the lobby share a crowd instead of
    all losing to the lowest index."""

    def __init__(self) -> None:
        self._last = -1

    def pick(self, scores: Sequence[float]) -> int:
        best = min(scores)
        n = len(scores)
        index = min(
            (i for i, s in enumerate(scores) if s == best),
            key=lambda i: (i - self._last - 1) % n,
        )
        self._last = index
        return index
