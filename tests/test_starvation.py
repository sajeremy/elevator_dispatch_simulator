"""Seat reservation: a car never boards a passenger while an older passenger of
its own, waiting ahead and going the same way, would be left without a seat.
Without it, a rider upstream of a busy origin is passed every time the car
fills there and waits until the stream of newer passengers dries up."""

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.simulation import run_simulation
from tests.helpers import requests


def config(**overrides) -> SimulationConfig:
    # One car: the dispatcher has no choice, so round robin keeps the test fast.
    return SimulationConfig(
        num_floors=10,
        num_elevators=1,
        dispatch=DispatchStrategy.ROUND_ROBIN,
        **overrides,
    )


def by_id(result):
    return {p.request.passenger_id: p for p in result.passengers}


def test_oldest_passenger_boards_on_the_first_pass_despite_a_lobby_crowd():
    # X waits at floor 5 going up. Two lobby passengers for floor 10 arrive
    # every tick for 60 ticks; a capacity-2 car fills at the lobby every trip.
    reqs = requests((0, "X", 5, 10))
    for t in range(60):
        reqs += requests((t, f"a{t}", 1, 10), (t, f"b{t}", 1, 10))
    result = run_simulation(reqs, config(capacity=2))
    x = by_id(result)["X"]
    # One seat is kept for X, so the car leaves the lobby with one rider,
    # reaches floor 5 at t=4 and boards X at t=5.
    assert x.pickup_time == 5
    assert result.completed


def test_reserved_seat_passes_a_newer_pickup_at_an_earlier_floor():
    # Capacity 1. X (older) waits at 9 going up, Y (newer) at 5 going up.
    # The car must pass Y without stopping and take X first.
    reqs = requests((0, "X", 9, 10), (0, "Y", 5, 10))
    result = run_simulation(reqs, config(capacity=1))
    p = by_id(result)
    assert p["X"].pickup_time == 8  # moves t=0..7 to floor 9, boards at t=8
    assert p["Y"].pickup_time > p["X"].pickup_time
    floors = [row[1] for row in result.positions.rows]
    assert floors[: p["X"].pickup_time].count(5) == 1  # through floor 5, no stop


def test_no_seat_is_reserved_for_an_older_pickup_going_the_other_way():
    # Capacity 1, car starts at 5. X (older) at 9 wants down; Y (newer) at 5
    # wants up. X is not ahead in Y's direction, so Y boards at once.
    reqs = requests((0, "X", 9, 2), (0, "Y", 5, 7))
    result = run_simulation(reqs, config(capacity=1, start_floor=5))
    p = by_id(result)
    assert p["Y"].pickup_time == 0
    assert p["X"].delivered
