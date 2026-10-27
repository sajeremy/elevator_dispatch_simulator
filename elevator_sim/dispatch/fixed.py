"""Replays a given assignment: each passenger goes to a preset car.

For benchmarks only (the offline optimum is checked by replaying its
assignment), so it is passed to `run_simulation(dispatcher=...)` and has no
DispatchStrategy entry.
"""

from collections.abc import Mapping, Sequence

from elevator_sim.models import ElevatorRequest, ElevatorView


class FixedDispatcher:
    def __init__(self, assignment: Mapping[str, int]) -> None:
        """`assignment` maps passenger id to elevator index."""
        self.assignment = assignment

    def assign(
        self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int
    ) -> int:
        try:
            return self.assignment[request.passenger_id]
        except KeyError:
            raise ValueError(
                f"no fixed assignment for {request.passenger_id!r}"
            ) from None
