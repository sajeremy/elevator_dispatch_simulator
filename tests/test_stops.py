"""Intermediate stops: stops a rider sits through between boarding and alighting."""

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.simulation import run_simulation
from elevator_sim.workloads import random_trips
from tests.helpers import requests


def stops(reqs, **config):
    result = run_simulation(
        reqs, SimulationConfig(num_floors=20, num_elevators=1, **config)
    )
    return {p.request.passenger_id: p.stops for p in result.passengers}


def test_drop_off_and_pickup_along_the_way_count():
    # a rides 1 -> 10. b gets off at 5; c gets on at 7. Neither is a's own stop.
    reqs = requests((0, "a", 1, 10), (0, "b", 1, 5), (0, "c", 7, 12))
    assert stops(reqs) == {"a": 2, "b": 0, "c": 1}  # c rides through a's stop at 10


def test_boarding_and_alighting_stops_are_not_counted():
    reqs = requests((0, "a", 1, 10), (0, "b", 1, 10))
    assert stops(reqs) == {"a": 0, "b": 0}


@pytest.mark.parametrize("stop_duration", [1, 3])
def test_a_long_stop_counts_once(stop_duration):
    reqs = requests((0, "a", 1, 10), (0, "b", 1, 5))
    assert stops(reqs, stop_duration=stop_duration)["a"] == 1


def test_with_one_tick_stops_extra_ride_time_is_exactly_the_stops():
    # A rider never moves away from their floor under LOOK, so with
    # stop_duration 1: travel = distance + 1 (alighting) + intermediate stops.
    config = SimulationConfig(num_floors=20, num_elevators=3, capacity=4)
    result = run_simulation(random_trips(200, 20, 300, seed=1), config)
    assert result.completed
    for p in result.passengers:
        assert p.travel == p.request.distance + 1 + p.stops, p.request.passenger_id
