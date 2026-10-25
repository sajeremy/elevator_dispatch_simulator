"""LOOK reaches an assigned passenger within 2 x (num_floors - 1) floors of
travel; every other tick of the wait is spent stopped for someone else.
Capacity is set high enough that cars never fill, which would break this."""

import random

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.models import Request
from elevator_sim.simulation import run_simulation


def random_requests(seed: int, n: int, floors: int, horizon: int) -> list[Request]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        source, dest = rng.sample(range(1, floors + 1), 2)
        out.append(Request.from_tuple((rng.randrange(horizon), f"p{i}", source, dest)))
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
        positions_log_path=None,
    )
    result = run_simulation(random_requests(seed, 200, floors, 400), config)
    assert result.completed

    rows = result.positions.rows
    for p in result.passengers:
        car = 1 + p.elevator
        before = [config.start_floor] + [row[car] for row in rows]  # before[k] = floor before tick k
        moves = sum(before[k + 1] != before[k] for k in range(p.request.time, p.pickup_time))
        assert moves <= 2 * (floors - 1), p.request.passenger_id
