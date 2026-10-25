"""Maps config enums to concrete strategy classes.

This is the only module that names concrete strategies, so adding one means
adding an enum member and a line here.
"""

from collections.abc import Callable

from elevator_sim.config import DispatchStrategy
from elevator_sim.dispatch.base import Dispatcher
from elevator_sim.dispatch.round_robin import RoundRobinDispatcher
from elevator_sim.movement.base import MovementPolicy
from elevator_sim.movement.look import LookPolicy

DISPATCHERS: dict[DispatchStrategy, Callable[[], Dispatcher]] = {
    DispatchStrategy.ROUND_ROBIN: RoundRobinDispatcher,
}


def make_dispatcher(strategy: DispatchStrategy) -> Dispatcher:
    return DISPATCHERS[strategy]()


def make_movement() -> MovementPolicy:
    # LOOK for every dispatcher comparison; SCAN would be wired here.
    return LookPolicy()
