"""Data types shared by every layer.

`ElevatorRequest` is validated input (pydantic). `Passenger` and `Elevator` are the
mutable simulation state; only `simulation.py` changes them. Strategies see
`ElevatorView`, a frozen snapshot.
"""

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Direction(IntEnum):
    """Signed so that `floor + direction` is the next floor."""

    DOWN = -1
    IDLE = 0
    UP = 1


class ElevatorRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: int = Field(ge=0, description="Time step at which the request is made.")
    passenger_id: str = Field(description="Unique identifier of the passenger.")
    source_floor: int = Field(ge=1, description="Floor the passenger is waiting on.")
    destination_floor: int = Field(
        ge=1, description="Floor the passenger wants to go to."
    )

    @model_validator(mode="after")
    def _not_a_zero_length_trip(self) -> Self:
        if self.source_floor == self.destination_floor:
            raise ValueError(
                f"request {self.passenger_id!r}: source and destination are both "
                f"floor {self.source_floor}"
            )
        return self

    @property
    def direction(self) -> Direction:
        return Direction.UP if self.destination_floor > self.source_floor else Direction.DOWN

    @property
    def distance(self) -> int:
        return abs(self.destination_floor - self.source_floor)

    @classmethod
    def from_tuple(cls, raw: tuple[int, str, int, int]) -> ElevatorRequest:
        """Build an ElevatorRequest from a (time, passenger_id, source_floor, destination_floor) tuple."""
        time, passenger_id, source_floor, destination_floor = raw
        return cls(
            time=time,
            passenger_id=passenger_id,
            source_floor=source_floor,
            destination_floor=destination_floor,
        )


@dataclass(slots=True)
class Passenger:
    request: ElevatorRequest
    elevator: int
    arrival_order: int  # position in the time-sorted input; breaks same-tick ties
    pickup_time: int | None = None
    dropoff_time: int | None = None

    @property
    def delivered(self) -> bool:
        return self.dropoff_time is not None

    @property
    def wait(self) -> int:
        assert self.pickup_time is not None
        return self.pickup_time - self.request.time

    @property
    def travel(self) -> int:
        assert self.pickup_time is not None and self.dropoff_time is not None
        return self.dropoff_time - self.pickup_time

    @property
    def total(self) -> int:
        return self.wait + self.travel

    @property
    def stretch(self) -> float:
        return self.total / self.request.distance


@dataclass(frozen=True, slots=True)
class PickupView:
    floor: int
    destination_floor: int  # known up front under destination dispatch
    direction: Direction
    request_time: int
    arrival_order: int


@dataclass(frozen=True, slots=True)
class ElevatorView:
    """Read-only snapshot of one car, handed to dispatchers and movement policies."""

    index: int
    floor: int
    direction: Direction
    load: int
    capacity: int
    dropoffs: tuple[int, ...]  # destination floor of each rider
    pickups: tuple[PickupView, ...]  # assigned passengers not yet boarded
    stop_ticks_left: int = 0  # ticks the car stays stopped after this one

    @property
    def has_room(self) -> bool:
        return self.load < self.capacity


@dataclass(slots=True)
class Elevator:
    index: int
    floor: int
    capacity: int
    direction: Direction = Direction.IDLE
    riders: list[Passenger] = field(default_factory=list)
    waiting: list[Passenger] = field(default_factory=list)  # assigned, not boarded
    stop_ticks_left: int = 0  # remaining ticks of the current stop after this one

    def view(self) -> ElevatorView:
        return ElevatorView(
            index=self.index,
            floor=self.floor,
            direction=self.direction,
            load=len(self.riders),
            capacity=self.capacity,
            dropoffs=tuple(p.request.destination_floor for p in self.riders),
            pickups=tuple(
                PickupView(
                    floor=p.request.source_floor,
                    destination_floor=p.request.destination_floor,
                    direction=p.request.direction,
                    request_time=p.request.time,
                    arrival_order=p.arrival_order,
                )
                for p in self.waiting
            ),
            stop_ticks_left=self.stop_ticks_left,
        )


class ActionKind(StrEnum):
    MOVE = "move"
    STOP = "stop"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class Action:
    """What a car does this tick.

    MOVE: travel one floor in `direction`.
    STOP: open doors here; `direction` is the way the car leaves afterwards,
          which decides who boards (only passengers going that way).
    IDLE: stay put with nothing to do.
    """

    kind: ActionKind
    direction: Direction

    def __post_init__(self) -> None:
        if self.kind is ActionKind.MOVE and self.direction is Direction.IDLE:
            raise ValueError("MOVE needs UP or DOWN")
        if self.kind is ActionKind.IDLE and self.direction is not Direction.IDLE:
            raise ValueError("IDLE has no direction")

    @classmethod
    def move(cls, direction: Direction) -> Action:
        return cls(ActionKind.MOVE, direction)

    @classmethod
    def stop(cls, departing: Direction) -> Action:
        return cls(ActionKind.STOP, departing)

    @classmethod
    def idle(cls) -> Action:
        return cls(ActionKind.IDLE, Direction.IDLE)
