"""Maps config enums to concrete strategy classes.

This is the only module that names concrete strategies, so adding one means
adding an enum member and a line here.
"""

from collections.abc import Callable

from .config import DispatchStrategy
from .dispatch import Dispatcher, RoundRobinDispatcher
from .movement import LookPolicy, MovementPolicy

DISPATCHERS: dict[DispatchStrategy, Callable[[], Dispatcher]] = {
    DispatchStrategy.ROUND_ROBIN: RoundRobinDispatcher,
}


def make_dispatcher(strategy: DispatchStrategy) -> Dispatcher:
    return DISPATCHERS[strategy]()


def make_movement() -> MovementPolicy:
    # LOOK for every dispatcher comparison; SCAN would be wired here.
    return LookPolicy()
