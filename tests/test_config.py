import pytest
from pydantic import ValidationError

from elevator_sim.config import DispatchStrategy, SimulationConfig


def test_defaults_are_valid():
    SimulationConfig()


def test_defaults_are_the_office_day_building():
    c = SimulationConfig()
    assert (c.num_floors, c.num_elevators, c.capacity) == (40, 8, 16)
    assert c.dispatch is DispatchStrategy.ETD


@pytest.mark.parametrize(
    "overrides",
    [
        {"num_floors": 1},
        {"num_elevators": 0},
        {"capacity": 0},
        {"start_floor": 0},
        {"stop_duration": 0},
        {"max_ticks": 0},
        {"num_floors": 10, "start_floor": 11},
    ],
)
def test_rejects_invalid_values(overrides):
    with pytest.raises(ValidationError):
        SimulationConfig(**overrides)


def test_is_frozen():
    with pytest.raises(ValidationError):
        SimulationConfig().capacity = 3
