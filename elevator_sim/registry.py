"""Maps config enums to concrete strategy classes.

This is the only module that names concrete strategies, so adding one means
adding an enum member and a line here.
"""

from collections.abc import Callable

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.dispatch.base import Dispatcher
from elevator_sim.dispatch.etd import EtdDispatcher
from elevator_sim.dispatch.round_robin import RoundRobinDispatcher
from elevator_sim.movement.base import MovementPolicy
from elevator_sim.movement.look import LookPolicy

# Each factory gets the run's config, for strategies that need building
# facts such as stop_duration.
DISPATCHERS: dict[DispatchStrategy, Callable[[SimulationConfig], Dispatcher]] = {
    DispatchStrategy.ROUND_ROBIN: lambda config: RoundRobinDispatcher(),
    DispatchStrategy.ETD: lambda config: EtdDispatcher(
        make_movement(),
        stop_duration=config.stop_duration,
        num_floors=config.num_floors,
        horizon=config.max_ticks,
    ),
}


def make_dispatcher(config: SimulationConfig) -> Dispatcher:
    return DISPATCHERS[config.dispatch](config)


def make_movement() -> MovementPolicy:
    # LOOK for every dispatcher comparison; SCAN would be wired here.
    return LookPolicy()
