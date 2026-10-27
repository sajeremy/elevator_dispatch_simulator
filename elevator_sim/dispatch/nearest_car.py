"""Direction-aware nearest car: send each request to the car that would reach
the caller in the fewest floors, judged from each car's position, direction
and assigned floors only.

    idle car:                                  |source - car|
    moving toward the caller, caller's way:    |source - car|
    anything else (moving away, or toward the
    caller but the other way):                 car -> end of its sweep -> source

The end of the sweep is the farthest assigned floor ahead of the car, where
LOOK turns around. Ties go to the lowest index.

Unlike ETD it ignores stop time, load and capacity, and the delay a new
passenger causes everyone else in the car. It is the middle comparison: how
far position and direction alone get, without predicting routes.
"""

from collections.abc import Sequence

from elevator_sim.models import Direction, ElevatorRequest, ElevatorView


class NearestCarDispatcher:
    def assign(
        self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int
    ) -> int:
        return min(
            range(len(elevators)),
            key=lambda i: (self.distance(elevators[i], request), i),
        )

    @staticmethod
    def distance(car: ElevatorView, request: ElevatorRequest) -> int:
        """Floors the car travels before reaching the caller."""
        source = request.source_floor
        if car.direction == Direction.IDLE:
            return abs(source - car.floor)
        ahead = (source - car.floor) * car.direction >= 0
        if ahead and request.direction == car.direction:
            return abs(source - car.floor)
        turn = _sweep_end(car)
        return abs(turn - car.floor) + abs(turn - source)


def _sweep_end(car: ElevatorView) -> int:
    """The farthest assigned floor ahead of the car, or its own floor if none."""
    floors = [*car.dropoffs, *(p.floor for p in car.pickups)]
    return max(
        (f for f in floors if (f - car.floor) * car.direction > 0),
        key=lambda f: abs(f - car.floor),
        default=car.floor,
    )
