"""The rules for one car's tick: stop (alight, then board) or move one floor.

The simulation applies them to live state. The ETD dispatcher applies them
to private copies to predict a route, so its predictions use exactly the
same physics as the run itself. `boarding` is the one boarding rule; LOOK
uses it too, so a car only stops where someone can actually get on.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from elevator_sim.models import (
    Action,
    ActionKind,
    Direction,
    Elevator,
    Passenger,
    PickupView,
)


class Activity(StrEnum):
    MOVING = "moving"
    STOPPED = "stopped"
    IDLE = "idle"


@dataclass(slots=True)
class TickOutcome:
    activity: Activity
    load: int  # riders aboard after this tick
    alighted: list[Passenger] = field(default_factory=list)
    boarded: list[Passenger] = field(default_factory=list)
    # Waiting passengers at the floor the car just left, going its way: they
    # saw their car and could not get on (full, or seats kept for older pickups).
    left_behind: list[Passenger] = field(default_factory=list)


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
            # A new stop is an intermediate one for every rider not getting off
            # here; passengers boarding now are not riders yet.
            for p in elevator.riders:
                if p.request.destination_floor != elevator.floor:
                    p.stops += 1
            return _exchange(elevator, t)
        case ActionKind.MOVE:
            floor = elevator.floor + action.direction
            if not 1 <= floor <= num_floors:
                raise ValueError(f"elevator {elevator.index} would leave the building")
            left_behind = [
                p
                for p in elevator.waiting
                if p.request.source_floor == elevator.floor
                and p.request.direction == action.direction
            ]
            for p in left_behind:
                p.left_behind += 1
            elevator.floor = floor
            elevator.direction = action.direction
            return TickOutcome(
                Activity.MOVING, load=len(elevator.riders), left_behind=left_behind
            )
        case ActionKind.IDLE:
            elevator.direction = Direction.IDLE
            return TickOutcome(Activity.IDLE, load=len(elevator.riders))


def boarding(
    pickups: Iterable[PickupView], floor: int, departing: Direction, room: int
) -> list[PickupView]:
    """Which pickups at `floor` board a car leaving in `departing` with `room`
    free seats: oldest request first.

    A seat is kept for every older pickup that lies ahead in `departing` and
    goes that way, so a car never fills with newer passengers while an older
    one waits further along the sweep. Without this, a rider upstream of a
    busy origin is passed every time the car fills there (test_starvation.py).
    """
    pickups = tuple(pickups)
    here = sorted(
        (p for p in pickups if p.floor == floor and p.direction == departing),
        key=lambda p: p.arrival_order,
    )
    boarders: list[PickupView] = []
    for p in here:
        reserved = sum(
            1
            for q in pickups
            if q.arrival_order < p.arrival_order
            and q.direction == departing
            and (q.floor - floor) * departing > 0
        )
        if len(boarders) + reserved >= room:
            break
        boarders.append(p)
    return boarders


def _exchange(elevator: Elevator, t: int) -> TickOutcome:
    """Alight riders for this floor, then board waiting passengers going the
    car's way, oldest request first, within the seats not reserved for older
    passengers ahead (see `boarding`)."""
    floor = elevator.floor
    alighting = [p for p in elevator.riders if p.request.destination_floor == floor]
    for p in alighting:
        p.dropoff_time = t
    elevator.riders = [p for p in elevator.riders if p.request.destination_floor != floor]

    room = elevator.capacity - len(elevator.riders)
    orders = {
        p.arrival_order
        for p in boarding(elevator.view().pickups, floor, elevator.direction, room)
    }
    boarders = sorted(
        (p for p in elevator.waiting if p.arrival_order in orders),
        key=lambda p: p.arrival_order,
    )
    for p in boarders:
        p.pickup_time = t
        elevator.waiting.remove(p)
        elevator.riders.append(p)
    return TickOutcome(
        Activity.STOPPED, load=len(elevator.riders), alighted=alighting, boarded=boarders
    )
