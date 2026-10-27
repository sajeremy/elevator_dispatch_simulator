import random

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.dispatch.etd import EtdDispatcher, pickup_view
from elevator_sim.models import Direction, ElevatorRequest, ElevatorView, PickupView
from elevator_sim.movement.look import LookPolicy
from elevator_sim.simulation import run_simulation

UP, IDLE = Direction.UP, Direction.IDLE


def etd(**overrides) -> EtdDispatcher:
    kwargs = {"stop_duration": 1, "num_floors": 40, "horizon": 10_000} | overrides
    return EtdDispatcher(LookPolicy(), **kwargs)


def car(index, floor, direction=IDLE, dropoffs=(), pickups=()) -> ElevatorView:
    return ElevatorView(
        index=index,
        floor=floor,
        direction=direction,
        load=len(dropoffs),
        capacity=12,
        dropoffs=tuple(dropoffs),
        pickups=tuple(pickups),
    )


def request(source, dest, time=0, pid="new") -> ElevatorRequest:
    return ElevatorRequest.from_tuple((time, pid, source, dest))


def test_idle_cars_nearest_wins():
    cars = [car(0, 1), car(1, 30)]
    assert etd().assign(request(28, 2), cars, t=0) == 1


def test_ties_rotate_through_the_cars():
    cars = [car(0, 5), car(1, 5), car(2, 5)]
    dispatcher = etd()
    picks = [dispatcher.assign(request(10, 2), cars, t=0) for _ in range(4)]
    assert picks == [0, 1, 2, 0]


def test_route_cost_is_remaining_time_to_destination_for_everyone():
    # Car at 10 going up with a rider for 20, seen at t=5: the rider alights at t=15.
    busy = car(0, 10, UP, dropoffs=[20])
    assert etd().route_cost(busy, t=5) == 10
    # Add a trip 12 -> 18 requested at t=0: boards t=7, alights t=14, and the
    # rider now alights at t=17. The five ticks already waited are not counted.
    extra = pickup_view(request(12, 18, time=0))
    assert etd().route_cost(busy, t=5, extra=extra) == (14 - 5) + (17 - 5)


def test_marginal_cost_counts_delay_to_existing_riders():
    # car0 at 10 going up with a rider to 20; new trip 12 -> 18.
    # New passenger: board at t=2, alight at t=9 -> 2 + 7.
    # Rider: two extra stops (12 and 18) -> +2.
    busy = car(0, 10, UP, dropoffs=[20])
    assert etd().marginal_cost(busy, pickup_view(request(12, 18)), t=0) == 11
    # Idle car at 1: board at t=11, alight at t=18 -> 11 + 7, nobody else delayed.
    assert etd().marginal_cost(car(1, 1), pickup_view(request(12, 18)), t=0) == 18
    assert etd().assign(request(12, 18), [busy, car(1, 1)], t=0) == 0


def test_prediction_respects_capacity():
    full = ElevatorView(
        index=0, floor=1, direction=IDLE, load=1, capacity=1, dropoffs=(5,), pickups=()
    )
    new = PickupView(
        floor=1, destination_floor=3, direction=UP, request_time=0, arrival_order=0
    )
    trips = etd().predict(full, t=0, extra=new)
    # Can't board at floor 1 while full: rides to 5, comes back for the new passenger.
    rider, passenger = trips
    assert rider.dropoff == 4
    assert passenger.pickup > rider.dropoff


class RecordingEtd:
    """Wraps EtdDispatcher and keeps each car's prediction from its last assignment."""

    def __init__(self, inner: EtdDispatcher) -> None:
        self.inner = inner
        self.count = 0
        self.last: dict[int, tuple[int, list]] = {}

    def assign(self, request, elevators, t):
        index = self.inner.assign(request, elevators, t)
        new = pickup_view(request, arrival_order=self.count)
        self.last[index] = (t, self.inner.predict(elevators[index], t, extra=new))
        self.count += 1
        return index


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("capacity", [2, 12])
def test_last_prediction_per_car_matches_the_run_exactly(seed, capacity):
    """After a car's final assignment nothing else changes its route, so the
    prediction made then must equal what the simulation does."""
    rng = random.Random(seed)
    reqs = []
    for i in range(60):
        source, dest = rng.sample(range(1, 21), 2)
        reqs.append(
            ElevatorRequest.from_tuple((rng.randrange(120), f"p{i}", source, dest))
        )
    config = SimulationConfig(
        num_floors=20, num_elevators=3, capacity=capacity, stop_duration=2
    )
    spy = RecordingEtd(etd(stop_duration=2, num_floors=20))
    result = run_simulation(reqs, config, dispatcher=spy)
    assert result.completed

    for index, (t, trips) in spy.last.items():
        mine = [p for p in result.passengers if p.elevator == index]
        by_order = {p.arrival_order: p for p in mine}
        waiting = [trip for trip in trips if trip.arrival_order is not None]
        for trip in waiting:
            actual = by_order[trip.arrival_order]
            assert (trip.pickup, trip.dropoff) == (
                actual.pickup_time,
                actual.dropoff_time,
            )
        riders_then = [p for p in mine if p.pickup_time < t <= p.dropoff_time]
        predicted_rider_dropoffs = sorted(
            trip.dropoff for trip in trips if trip.pickup is None
        )
        assert predicted_rider_dropoffs == sorted(p.dropoff_time for p in riders_then)


def test_route_longer_than_the_horizon_is_a_value_error():
    # The horizon is the run's max_ticks: a cap too small for a route is a
    # config-versus-input conflict, reported like any other bad setting.
    with pytest.raises(ValueError, match="exceeds 3 ticks"):
        etd(horizon=3).predict(car(0, 1, UP, dropoffs=[20]), t=0)
