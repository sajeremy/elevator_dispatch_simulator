import pytest

from elevator_sim.config import SimulationConfig
from elevator_sim.dispatch.fixed import FixedDispatcher
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE


def test_replays_the_given_assignment():
    assignment = {"passenger1": 2, "passenger2": 2, "passenger3": 0}
    result = run_simulation(
        SAMPLE, SimulationConfig(), dispatcher=FixedDispatcher(assignment)
    )
    assert [p.elevator for p in result.passengers] == [2, 2, 0]


def test_missing_passenger_is_an_error():
    with pytest.raises(ValueError, match="passenger3"):
        run_simulation(
            SAMPLE,
            SimulationConfig(),
            dispatcher=FixedDispatcher({"passenger1": 0, "passenger2": 1}),
        )
