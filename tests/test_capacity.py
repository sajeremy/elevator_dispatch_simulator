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


def test_never_exceeds_capacity_and_leftovers_wait_for_the_same_car():
    reqs = requests(*[(0, f"p{i}", 1, 5) for i in range(5)])
    result = run_simulation(reqs, config(capacity=2))
    p = {x.request.passenger_id: x for x in result.passengers}

    # FIFO by input order: p0, p1 first trip; p2, p3 second; p4 third.
    assert [p[f"p{i}"].pickup_time for i in range(5)] == [0, 0, 10, 10, 20]
    assert all(x.elevator == 0 for x in result.passengers)
    assert result.completed


def test_full_car_does_not_stop_for_a_pickup_it_cannot_board():
    # Car fills at floor 1 going to 9; c waits at 4 going up.
    reqs = requests((0, "a", 1, 9), (0, "b", 1, 9), (0, "c", 4, 6))
    result = run_simulation(reqs, config(capacity=2))
    rows = [r[1] for r in result.positions.rows]
    assert rows[:10] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 9]  # no stop at floor 4
    c = next(x for x in result.passengers if x.request.passenger_id == "c")
    assert c.pickup_time > 9  # collected after the car empties


def test_capacity_one_still_serves_everyone():
    reqs = requests(*[(t, f"p{t}", 1 + t % 9, 10 - t % 9) for t in range(0, 30, 3)])
    result = run_simulation(reqs, config(capacity=1))
    assert result.completed
    assert all(x.delivered for x in result.passengers)


def test_full_car_that_empties_here_boards_in_the_same_stop():
    # a rides 1 -> 5 in a capacity-1 car; b waits at 5 going up. The car is
    # full on arrival but empties there, so b boards in the same stop.
    reqs = requests((0, "a", 1, 5), (0, "b", 5, 8))
    result = run_simulation(reqs, config(capacity=1))
    p = {x.request.passenger_id: x for x in result.passengers}
    assert p["a"].dropoff_time == p["b"].pickup_time == 5
    assert result.elevator_stats[0].stopped_ticks == 3  # board a; swap; alight b
