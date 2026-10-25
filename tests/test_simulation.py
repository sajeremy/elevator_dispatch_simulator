import csv

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE, requests


def config(**overrides) -> SimulationConfig:
    return SimulationConfig(**overrides)


def by_id(result):
    return {p.request.passenger_id: p for p in result.passengers}


def test_sample_input_hand_traced():
    # Round robin: p1 -> e0, p2 -> e1, p3 -> e2, all cars start at floor 1.
    result = run_simulation(SAMPLE, config())
    p = by_id(result)

    # p1: boards at t=0, moves t=1..50, alights at t=51.
    assert (p["passenger1"].pickup_time, p["passenger1"].dropoff_time) == (0, 51)
    # p2: boards at t=0, moves t=1..36, alights at t=37.
    assert (p["passenger2"].pickup_time, p["passenger2"].dropoff_time) == (0, 37)
    # p3: e2 moves t=10..28 to floor 20, boards at t=29, moves t=30..48, alights t=49.
    assert (p["passenger3"].pickup_time, p["passenger3"].dropoff_time) == (29, 49)

    assert result.completed
    assert result.ticks == 52  # t = 0..51
    assert [s.passengers_served for s in result.elevator_stats] == [1, 1, 1, 0]


def test_positions_log_one_row_per_tick_from_zero(tmp_path):
    path = tmp_path / "positions.csv"
    result = run_simulation(SAMPLE, config())
    result.positions.write_csv(path)
    rows = list(csv.reader(path.open()))
    assert rows[0] == ["time", "e0", "e1", "e2", "e3"]
    assert [int(r[0]) for r in rows[1:]] == list(range(result.ticks))
    assert rows[1] == ["0", "1", "1", "1", "1"]  # boarding tick, nobody has moved
    assert rows[2] == ["1", "2", "2", "1", "1"]
    assert rows[1 + 29] == ["29", "30", "30", "20", "1"]  # e2 stopped at floor 20


def test_clock_ticks_through_idle_gaps():
    result = run_simulation(requests((20, "a", 1, 2)), config(num_elevators=1))
    assert result.positions.rows[0] == (0, 1)
    assert [row[0] for row in result.positions.rows] == list(range(result.ticks))
    assert by_id(result)["a"].pickup_time == 20


def test_no_requests_records_t0_only():
    result = run_simulation([], config())
    assert result.ticks == 1 and result.completed


def test_max_ticks_stops_the_run():
    result = run_simulation(SAMPLE, config(max_ticks=10))
    assert result.ticks == 10
    assert not result.completed


def test_stop_duration_holds_the_car():
    result = run_simulation(requests((0, "a", 1, 3)), config(num_elevators=1, stop_duration=3))
    a = by_id(result)["a"]
    # Boarding stop t=0..2, moves t=3..4, alighting stop starts t=5.
    assert (a.pickup_time, a.dropoff_time) == (0, 5)
    # The run ends on the last drop-off tick; the rest of that stop isn't simulated.
    assert [row[1] for row in result.positions.rows] == [1, 1, 1, 2, 3, 3]


def test_late_arrival_boards_during_open_doors():
    reqs = requests((0, "a", 1, 3), (1, "b", 1, 4))
    result = run_simulation(reqs, config(num_elevators=1, stop_duration=3))
    assert by_id(result)["b"].pickup_time == 1


def test_opposite_direction_waits_for_the_return_sweep():
    # One car: a rides 1 -> 10. b at floor 5 wants down; the car passes 5 going up.
    reqs = requests((0, "a", 1, 10), (0, "b", 5, 2))
    result = run_simulation(reqs, config(num_floors=10, num_elevators=1))
    p = by_id(result)
    assert p["a"].dropoff_time == 10
    # Back down from 10 to 5 (t=11..15), board at t=16.
    assert p["b"].pickup_time == 16
    assert p["b"].dropoff_time == 16 + 3 + 1


def test_invalid_dispatcher_choice_is_rejected():
    class Bad:
        def assign(self, request, elevators, t):
            return 7

    with pytest.raises(ValueError, match="invalid elevator"):
        run_simulation(SAMPLE, config(), dispatcher=Bad())
