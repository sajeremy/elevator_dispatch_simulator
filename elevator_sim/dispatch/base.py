from collections.abc import Sequence
from typing import Protocol

from elevator_sim.models import ElevatorView, Request


class Dispatcher(Protocol):
    """Chooses the car for a new request. The choice is permanent."""

    def assign(self, request: Request, elevators: Sequence[ElevatorView], t: int) -> int:
        """Return the index of the elevator that will serve `request`."""
        ...
