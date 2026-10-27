"""ETD (estimated time to destination) dispatcher: assign each request to
the car whose passengers lose the least time by taking it.

Unlike an ETA (estimated time of arrival) dispatcher, which scores only how
soon a car reaches the caller, ETD scores whole journeys: the new
passenger's wait and ride, plus the delay to everyone already assigned.

For every car, predict its LOOK route twice from the current tick: once with
its current passengers and once with the new one added. The car's cost is
the time still ahead until each of its passengers reaches their destination,
riders and waiting passengers alike:

    cost = sum over passengers of (drop-off tick - now)

The new request goes to the car with the smallest increase (with - without);
ties rotate through the cars. The increase counts the new passenger's own wait
and travel plus the delay every existing passenger of that car takes on (extra
stops, a later turnaround, a full car). Minimizing it is minimizing the sum of
total time, the headline objective: a passenger's total is their drop-off tick
minus their request tick, and the request tick is fixed, so it cancels out of
the difference between the two routes.

Predictions run `physics.step` and the movement policy on a private copy of
the car, so they follow the simulation's rules exactly. They are exact unless
the car is assigned another request later. Only requests already released are
known (no peeking).
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass

from elevator_sim.dispatch.base import RotatingTies
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


class EtdDispatcher:
    def __init__(
        self,
        movement: MovementPolicy,
        *,
        stop_duration: int,
        num_floors: int,
        horizon: int,
    ) -> None:
        """`horizon` caps how many ticks a prediction may run (the run's max_ticks)."""
        self.movement = movement
        self.stop_duration = stop_duration
        self.num_floors = num_floors
        self.horizon = horizon
        self._ties = RotatingTies()

    def assign(
        self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int
    ) -> int:
        new = pickup_view(request)
        return self._ties.pick([self.marginal_cost(e, new, t) for e in elevators])

    def marginal_cost(self, car: ElevatorView, new: PickupView, t: int) -> int:
        return self.route_cost(car, t, extra=new) - self.route_cost(car, t)

    def route_cost(
        self, car: ElevatorView, t: int, extra: PickupView | None = None
    ) -> int:
        """Ticks from `t` until each passenger of the car (plus `extra`) is
        delivered, summed over all of them."""
        return sum(trip.dropoff - t for trip in self.predict(car, t, extra))

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
                # The horizon is the run's max_ticks: a cap too small for a
                # route is a config-versus-input conflict, like a floor
                # outside the building.
                raise ValueError(
                    f"route for elevator {car.index} exceeds {self.horizon} ticks "
                    "(max_ticks is ETD's prediction horizon; raise it)"
                )
            action = (
                None
                if elevator.stop_ticks_left > 0
                else self.movement.next_action(elevator.view())
            )
            step(
                elevator,
                action,
                tick,
                stop_duration=self.stop_duration,
                num_floors=self.num_floors,
            )
            tick += 1

        return [PredictedTrip(None, None, p.dropoff_time) for p in riders] + [
            PredictedTrip(p.arrival_order, p.pickup_time, p.dropoff_time)
            for p in waiting
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
