from typing import Protocol

from ..models import Action, ElevatorView


class MovementPolicy(Protocol):
    """Decides what one car does this tick, from its snapshot alone."""

    def next_action(self, elevator: ElevatorView) -> Action: ...
