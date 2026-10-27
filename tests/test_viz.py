"""Charts are drawn from the results a command just produced."""

import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.models import ElevatorRequest, Passenger
from elevator_sim.simulation import run_simulation
from elevator_sim.viz import benchmark_ratios, hourly, wait_by_hour
from elevator_sim.workloads import random_trips

PNG = b"\x89PNG\r\n\x1a\n"


def passenger(request_time, pickup_time):
    p = Passenger(
        ElevatorRequest.from_tuple((request_time, "x", 1, 5)),
        elevator=0,
        arrival_order=0,
    )
    p.pickup_time = pickup_time
    return p


@pytest.fixture(scope="module")
def runs():
    reqs = random_trips(120, 20, 600, seed=3)
    return {
        s: run_simulation(
            reqs, SimulationConfig(num_floors=20, num_elevators=3, dispatch=s)
        )
        for s in ("round_robin", "etd")
    }


def test_hourly_buckets_by_request_tick():
    rows = [
        passenger(0, 2),
        passenger(50, 54),
        passenger(100, 110),
        passenger(199, 219),
    ]
    buckets = hourly(rows, ticks_per_hour=100, start_hour=7)
    assert [(b.hour, b.trips, b.mean_wait, b.p95_wait) for b in buckets] == [
        (7, 2, 3.0, 4),
        (8, 2, 15.0, 20),
    ]


def test_hourly_leaves_out_passengers_never_picked_up():
    assert hourly([passenger(0, None)]) == []


def assert_png(path):
    data = path.read_bytes()
    assert data.startswith(PNG) and len(data) > 5_000, path


def test_wait_by_hour_writes_a_png(runs, tmp_path):
    wait_by_hour(
        [(s, r.passengers) for s, r in runs.items()],
        tmp_path / "h.png",
        ticks_per_hour=100,
    )
    assert_png(tmp_path / "h.png")


def test_wait_by_hour_with_no_pickups_still_writes_a_png(tmp_path):
    wait_by_hour([("etd", [passenger(0, None)])], tmp_path / "empty.png")
    assert_png(tmp_path / "empty.png")


def test_benchmark_ratios_writes_a_png(tmp_path):
    scenarios = [
        (
            "light",
            {
                "round_robin": (1.30, 1.67),
                "nearest_car": (1.09, 1.62),
                "etd": (1.04, 1.24),
            },
        ),
        (
            "burst",
            {
                "round_robin": (1.37, 1.98),
                "nearest_car": (1.19, 1.69),
                "etd": (1.12, 1.53),
            },
        ),
    ]
    benchmark_ratios(scenarios, tmp_path / "b.png")
    assert_png(tmp_path / "b.png")
