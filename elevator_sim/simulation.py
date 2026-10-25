"""The tick loop: the only code that mutates simulation state.

Each tick, in order:
  1. Ingest  - requests due at t, from the no-peek source
  2. Assign  - dispatcher picks a car for each new passenger (permanent)
  3. Decide  - movement policy picks an action for each car not mid-stop
  4. Apply   - alight/board (a stop) or move one floor; stamp times
  5. Record  - one positions row
The loop ends once every request is released and delivered, or at max_ticks.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from elevator_sim import registry
from elevator_sim.config import SimulationConfig
from elevator_sim.dispatch.base import Dispatcher
from elevator_sim.models import (
    Action,
    ActionKind,
    Direction,
    Elevator,
    ElevatorRequest,
    Passenger,
)
from elevator_sim.movement.base import MovementPolicy
from elevator_sim.recorder import PositionRecorder
from elevator_sim.requests import RequestSource


@dataclass(slots=True)
class ElevatorStats:
    moving_ticks: int = 0
    stopped_ticks: int = 0
    idle_ticks: int = 0
    passengers_served: int = 0

    @property
    def busy_ticks(self) -> int:
        return self.moving_ticks + self.stopped_ticks


@dataclass(frozen=True, slots=True)
class SimulationResult:
    config: SimulationConfig
    passengers: Sequence[Passenger]
    elevator_stats: Sequence[ElevatorStats]
    positions: PositionRecorder
    ticks: int  # number of recorded ticks (t = 0 .. ticks - 1)
    completed: bool  # False if max_ticks cut the run short


def run_simulation(
    requests: Iterable[ElevatorRequest],
    config: SimulationConfig,
    *,
    dispatcher: Dispatcher | None = None,
    movement: MovementPolicy | None = None,
) -> SimulationResult:
    """Run one simulation. Strategies default to those named in `config`;
    passing them explicitly is for benchmarks (e.g. a fixed assignment)."""
    dispatcher = dispatcher or registry.make_dispatcher(config.dispatch)
    movement = movement or registry.make_movement()

    source = RequestSource(requests, config.num_floors)
    elevators = [
        Elevator(index=i, floor=config.start_floor, capacity=config.capacity)
        for i in range(config.num_elevators)
    ]
    stats = [ElevatorStats() for _ in elevators]
    recorder = PositionRecorder(config.num_elevators)
    passengers: list[Passenger] = []
    undelivered = 0

    t = 0
    while t < config.max_ticks:
        for request in source.arrivals_at(t):
            views = [e.view() for e in elevators]
            index = dispatcher.assign(request, views, t)
            if not 0 <= index < len(elevators):
                raise ValueError(f"dispatcher returned invalid elevator {index}")
            passenger = Passenger(request, elevator=index, arrival_order=len(passengers))
            passengers.append(passenger)
            elevators[index].waiting.append(passenger)
            undelivered += 1

        actions = [
            None if e.stop_ticks_left > 0 else movement.next_action(e.view())
            for e in elevators
        ]

        for elevator, action in zip(elevators, actions):
            undelivered -= _apply(elevator, action, t, config, stats[elevator.index])

        recorder.record(t, [e.floor for e in elevators])

        t += 1
        if source.exhausted and undelivered == 0:
            break

    if config.positions_log_path is not None:
        recorder.write_csv(config.positions_log_path)

    return SimulationResult(
        config=config,
        passengers=passengers,
        elevator_stats=stats,
        positions=recorder,
        ticks=t,
        completed=source.exhausted and undelivered == 0,
    )


def _apply(
    elevator: Elevator,
    action: Action | None,
    t: int,
    config: SimulationConfig,
    stats: ElevatorStats,
) -> int:
    """Carry out one car's tick. Returns how many passengers alighted."""
    if action is None:  # still mid-stop: doors stay open
        elevator.stop_ticks_left -= 1
        stats.stopped_ticks += 1
        return _exchange(elevator, t, stats)

    match action.kind:
        case ActionKind.STOP:
            elevator.direction = action.direction
            elevator.stop_ticks_left = config.stop_duration - 1
            stats.stopped_ticks += 1
            return _exchange(elevator, t, stats)
        case ActionKind.MOVE:
            floor = elevator.floor + action.direction
            if not 1 <= floor <= config.num_floors:
                raise ValueError(f"elevator {elevator.index} would leave the building")
            elevator.floor = floor
            elevator.direction = action.direction
            stats.moving_ticks += 1
        case ActionKind.IDLE:
            elevator.direction = Direction.IDLE
            stats.idle_ticks += 1
    return 0


def _exchange(elevator: Elevator, t: int, stats: ElevatorStats) -> int:
    """Alight riders for this floor, then board waiting passengers going the
    car's way, oldest request first, up to capacity."""
    floor = elevator.floor
    alighting = [p for p in elevator.riders if p.request.destination_floor == floor]
    for p in alighting:
        p.dropoff_time = t
    elevator.riders = [p for p in elevator.riders if p.request.destination_floor != floor]
    stats.passengers_served += len(alighting)

    boarding = [
        p
        for p in elevator.waiting
        if p.request.source_floor == floor and p.request.direction == elevator.direction
    ]
    boarding.sort(key=lambda p: p.arrival_order)
    boarding = boarding[: elevator.capacity - len(elevator.riders)]
    for p in boarding:
        p.pickup_time = t
        elevator.waiting.remove(p)
        elevator.riders.append(p)
    return len(alighting)
