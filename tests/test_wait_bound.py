"""Wait bounds under LOOK, in floors of travel (every other tick of a wait is
spent stopped for someone else).

1. With capacity that never binds, a car reaches an assigned passenger within
   2 x (num_floors - 1) floors.
2. With any capacity, once a passenger is the oldest still waiting for their
   car, seat reservation keeps a seat for them, so newer passengers can never
   overtake them. If the car has a free seat at that moment they board within
   one sweep, 2 x (num_floors - 1) floors; if it is full of older riders it
   first finishes that leg (at most num_floors - 1 more floors).
"""

import random

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.models import ElevatorRequest
from elevator_sim.simulation import run_simulation


def random_requests(seed: int, n: int, floors: int, horizon: int) -> list[ElevatorRequest]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        source, dest = rng.sample(range(1, floors + 1), 2)
        out.append(ElevatorRequest.from_tuple((rng.randrange(horizon), f"p{i}", source, dest)))
    return out


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("stop_duration", [1, 3])
def test_travel_while_waiting_is_bounded(seed, stop_duration):
    floors = 20
    config = SimulationConfig(
        num_floors=floors,
        num_elevators=3,
        capacity=1_000,
        stop_duration=stop_duration,
    )
    result = run_simulation(random_requests(seed, 200, floors, 400), config)
    assert result.completed

    rows = result.positions.rows
    for p in result.passengers:
        car = 1 + p.elevator
        before = [config.start_floor] + [row[car] for row in rows]  # before[k] = floor before tick k
        moves = sum(before[k + 1] != before[k] for k in range(p.request.time, p.pickup_time))
        assert moves <= 2 * (floors - 1), p.request.passenger_id


def floors_travelled(result, passenger, start: int) -> int:
    """Floors the passenger's car moves between tick `start` and the pickup."""
    car = 1 + passenger.elevator
    before = [result.config.start_floor] + [row[car] for row in result.positions.rows]
    return sum(
        before[k + 1] != before[k] for k in range(start, passenger.pickup_time)
    )


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("capacity", [2, 4, 1_000])
def test_oldest_waiting_passenger_boards_within_one_sweep(seed, capacity):
    floors = 20
    config = SimulationConfig(num_floors=floors, num_elevators=3, capacity=capacity)
    result = run_simulation(random_requests(seed, 200, floors, 400), config)
    assert result.completed

    for p in result.passengers:
        same_car = [q for q in result.passengers if q.elevator == p.elevator]
        older = [q for q in same_car if q.arrival_order < p.arrival_order]
        # The tick from which p is the oldest passenger still waiting for its car.
        oldest_from = max([p.request.time, *(q.pickup_time for q in older)])
        aboard = sum(
            q.pickup_time <= oldest_from < q.dropoff_time for q in same_car
        )
        legs = 2 if aboard < capacity else 3
        assert floors_travelled(result, p, oldest_from) <= legs * (floors - 1), (
            p.request.passenger_id
        )
