import pytest
from pydantic import ValidationError

from elevator_sim.config import SimulationConfig


def test_defaults_are_valid():
    SimulationConfig()


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
