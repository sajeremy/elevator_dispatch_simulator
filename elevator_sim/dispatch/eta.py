"""ETA cost dispatcher: assign each request to the car whose passengers lose
the least time by taking it.

For every car, predict its LOOK route twice from the current tick: once with
its current passengers and once with the new one added. The car's cost is
the time its passengers still need:

    waiting passenger:  wait_weight * (pickup - now) + (dropoff - pickup)
    rider on board:     dropoff - now

The new request goes to the car with the smallest increase (with - without),
ties to the lowest index. The increase counts the new passenger's own wait and
travel plus the delay every existing passenger of that car takes on (extra
stops, a later turnaround, a full car).

Predictions run `physics.step` and the movement policy on a private copy of
the car, so they follow the simulation's rules exactly. They are exact unless
the car is assigned another request later. Only requests already released are
known (no peeking).
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass

from elevator_sim.models import (
    Elevator,
    ElevatorRequest,
    ElevatorView,
    Passenger,
    PickupView,
)
from elevator_sim.movement.base import MovementPolicy
from elevator_sim.physics import step

# A new request is the latest arrival, so it boards after everyone already waiting.
_NEWEST = sys.maxsize


@dataclass(frozen=True, slots=True)
class PredictedTrip:
    arrival_order: int | None  # None for a rider already on board
    pickup: int | None  # None for a rider already on board
    dropoff: int


def pickup_view(request: ElevatorRequest, arrival_order: int = _NEWEST) -> PickupView:
    return PickupView(
        floor=request.source_floor,
        destination_floor=request.destination_floor,
        direction=request.direction,
        request_time=request.time,
        arrival_order=arrival_order,
    )


class EtaDispatcher:
    def __init__(
        self,
        movement: MovementPolicy,
        *,
        stop_duration: int,
        num_floors: int,
        horizon: int,
        wait_weight: float = 1.0,
    ) -> None:
        """`horizon` caps how many ticks a prediction may run (the run's max_ticks).
        `wait_weight` > 1 values a tick of waiting above a tick of riding."""
        self.movement = movement
        self.stop_duration = stop_duration
        self.num_floors = num_floors
        self.horizon = horizon
        self.wait_weight = wait_weight

    def assign(self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int) -> int:
        new = pickup_view(request)
        return min(
            range(len(elevators)),
            key=lambda i: (self.marginal_cost(elevators[i], new, t), i),
        )

    def marginal_cost(self, car: ElevatorView, new: PickupView, t: int) -> float:
        return self.route_cost(car, t, extra=new) - self.route_cost(car, t)

    def route_cost(self, car: ElevatorView, t: int, extra: PickupView | None = None) -> float:
        cost = 0.0
        for trip in self.predict(car, t, extra):
            if trip.pickup is None:
                cost += trip.dropoff - t
            else:
                cost += self.wait_weight * (trip.pickup - t) + (trip.dropoff - trip.pickup)
        return cost

    def predict(
        self, car: ElevatorView, t: int, extra: PickupView | None = None
    ) -> list[PredictedTrip]:
        """Run the car alone from tick t until its passengers (plus `extra`) are delivered."""
        elevator = _rebuild(car, extra)
        riders = list(elevator.riders)
        waiting = list(elevator.waiting)

        tick = t
        while elevator.riders or elevator.waiting:
            if tick - t >= self.horizon:
                raise RuntimeError(f"route for elevator {car.index} exceeds {self.horizon} ticks")
            action = None if elevator.stop_ticks_left > 0 else self.movement.next_action(elevator.view())
            step(
                elevator,
                action,
                tick,
                stop_duration=self.stop_duration,
                num_floors=self.num_floors,
            )
            tick += 1

        return [PredictedTrip(None, None, p.dropoff_time) for p in riders] + [
            PredictedTrip(p.arrival_order, p.pickup_time, p.dropoff_time) for p in waiting
        ]


def _rebuild(car: ElevatorView, extra: PickupView | None) -> Elevator:
    """A private Elevator equivalent to the snapshot. Requests are built with
    model_construct: the values come from already-validated requests."""
    riders = [
        # A rider's origin no longer matters (it only decides who boards), so
        # the current floor stands in for it.
        Passenger(
            ElevatorRequest.model_construct(
                time=0, passenger_id="", source_floor=car.floor, destination_floor=floor
            ),
            elevator=car.index,
            arrival_order=-1,
        )
        for floor in car.dropoffs
    ]
    pickups = [*car.pickups, extra] if extra is not None else car.pickups
    waiting = [
        Passenger(
            ElevatorRequest.model_construct(
                time=p.request_time,
                passenger_id="",
                source_floor=p.floor,
                destination_floor=p.destination_floor,
            ),
            elevator=car.index,
            arrival_order=p.arrival_order,
        )
        for p in pickups
    ]
    return Elevator(
        index=car.index,
        floor=car.floor,
        capacity=car.capacity,
        direction=car.direction,
        riders=riders,
        waiting=waiting,
        stop_ticks_left=car.stop_ticks_left,
    )
