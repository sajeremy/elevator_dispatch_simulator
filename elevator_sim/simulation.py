"""The tick loop: the only code that mutates live simulation state.

Per-car rules (stop, board, alight, move) live in `physics.py`.

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
from elevator_sim.elevator_requests import RequestSource
from elevator_sim.models import Elevator, ElevatorRequest, Passenger
from elevator_sim.movement.base import MovementPolicy
from elevator_sim.physics import Activity, TickOutcome, step
from elevator_sim.recorder import PositionRecorder


@dataclass(slots=True)
class ElevatorStats:
    capacity: int
    moving_ticks: int = 0
    stopped_ticks: int = 0
    idle_ticks: int = 0
    passengers_served: int = 0
    max_load: int = 0
    full_ticks: int = 0  # ticks ending with every seat taken
    empty_moving_ticks: int = 0  # moving with nobody aboard (deadheading)
    left_behind: int = 0  # departures that left a same-direction pickup behind

    @property
    def busy_ticks(self) -> int:
        return self.moving_ticks + self.stopped_ticks

    def count(self, outcome: TickOutcome) -> None:
        match outcome.activity:
            case Activity.MOVING:
                self.moving_ticks += 1
                if outcome.load == 0:
                    self.empty_moving_ticks += 1
            case Activity.STOPPED:
                self.stopped_ticks += 1
            case Activity.IDLE:
                self.idle_ticks += 1
        self.passengers_served += len(outcome.alighted)
        self.max_load = max(self.max_load, outcome.load)
        if outcome.load == self.capacity:
            self.full_ticks += 1
        self.left_behind += len(outcome.left_behind)


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
    dispatcher = dispatcher or registry.make_dispatcher(config)
    movement = movement or registry.make_movement()

    source = RequestSource(requests, config.num_floors, max_ticks=config.max_ticks)
    elevators = [
        Elevator(index=i, floor=config.start_floor, capacity=config.capacity)
        for i in range(config.num_elevators)
    ]
    stats = [ElevatorStats(capacity=config.capacity) for _ in elevators]
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
            outcome = step(
                elevator,
                action,
                t,
                stop_duration=config.stop_duration,
                num_floors=config.num_floors,
            )
            stats[elevator.index].count(outcome)
            undelivered -= len(outcome.alighted)

        recorder.record(t, [e.floor for e in elevators])

        t += 1
        if source.exhausted and undelivered == 0:
            break

    return SimulationResult(
        config=config,
        passengers=passengers,
        elevator_stats=stats,
        positions=recorder,
        ticks=t,
        completed=source.exhausted and undelivered == 0,
    )

