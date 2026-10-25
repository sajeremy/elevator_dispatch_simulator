from collections.abc import Sequence

from elevator_sim.models import ElevatorRequest, ElevatorView


class RoundRobinDispatcher:
    """Baseline: cars take turns, ignoring position, direction and load."""

    def __init__(self) -> None:
        self._turn = 0

    def assign(self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int) -> int:
        index = self._turn % len(elevators)
        self._turn += 1
        return index
