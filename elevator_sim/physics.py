"""The rules for one car's tick: stop (alight, then board) or move one floor.

The simulation applies them to live state. The ETA dispatcher applies them
to private copies to predict a route, so its predictions use exactly the
same physics as the run itself.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from elevator_sim.models import Action, ActionKind, Direction, Elevator, Passenger


class Activity(StrEnum):
    MOVING = "moving"
    STOPPED = "stopped"
    IDLE = "idle"


@dataclass(slots=True)
class TickOutcome:
    activity: Activity
    alighted: list[Passenger] = field(default_factory=list)
    boarded: list[Passenger] = field(default_factory=list)


def step(
    elevator: Elevator,
    action: Action | None,
    t: int,
    *,
    stop_duration: int,
    num_floors: int,
) -> TickOutcome:
    """Carry out one car's tick. `action` is None while the car is mid-stop."""
    if action is None:  # doors stay open
        elevator.stop_ticks_left -= 1
        return _exchange(elevator, t)

    match action.kind:
        case ActionKind.STOP:
            elevator.direction = action.direction
            elevator.stop_ticks_left = stop_duration - 1
            return _exchange(elevator, t)
        case ActionKind.MOVE:
            floor = elevator.floor + action.direction
            if not 1 <= floor <= num_floors:
                raise ValueError(f"elevator {elevator.index} would leave the building")
            elevator.floor = floor
            elevator.direction = action.direction
            return TickOutcome(Activity.MOVING)
        case ActionKind.IDLE:
            elevator.direction = Direction.IDLE
            return TickOutcome(Activity.IDLE)


def _exchange(elevator: Elevator, t: int) -> TickOutcome:
    """Alight riders for this floor, then board waiting passengers going the
    car's way, oldest request first, up to capacity."""
    floor = elevator.floor
    alighting = [p for p in elevator.riders if p.request.destination_floor == floor]
    for p in alighting:
        p.dropoff_time = t
    elevator.riders = [p for p in elevator.riders if p.request.destination_floor != floor]

    boarding = [
        p
        for p in elevator.waiting
        if p.request.source_floor == floor and p.request.direction == elevator.direction
    ]
    boarding.sort(key=lambda p: p.arrival_order)
    boarding = boarding[: elevator.capacity - len(elevator.riders)]
    for p in boarding:
        p.pickup_time = t
        elevator.waiting.remove(p)
        elevator.riders.append(p)
    return TickOutcome(Activity.STOPPED, alighted=alighting, boarded=boarding)
