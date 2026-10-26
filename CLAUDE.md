# Elevator Dispatch Simulator: Design Notes

Working design notes for the project. Problem statement: `docs/challenge.md`.

Conventions:
- Non-obvious choices are recorded with their trade-offs.
- Changes are small and reviewable.
- Scope is fixed to the build order below; anything beyond it is a deliberate addition.

## Requirements (interpretation of the problem statement)

- **Time:** 1 tick = 1 floor of travel. The loop advances exactly one tick at a time, including idle stretches where no requests arrive. No event-driven clock jumping; event-driven simulation is noted as a scaling improvement.
- **Input:** a list of requests (`time,id,source,dest`). No stream implementation. The scheduler must never see requests with `time > t`. This is enforced in one place, `RequestSource.arrivals_at(t)`, so swapping to a stream later is a one-class change.
- **Destination dispatch:** each passenger is assigned to one elevator at request time. Assignment is permanent.
- **Output:** (1) a positions CSV, one row per tick, starting at t=0: `time,e0,e1,...`; (2) end-of-run stats: min, max and average of wait and total time, plus p95, stretch, per-elevator utilization and any notable observations.
- **Definitions:** wait = request time → pickup. Travel = pickup → drop-off. Total = wait + travel. Stretch = total ÷ |dest − source|.

## Architecture (layers; a layer calls only layers below it)

| Layer | Modules | Role |
|---|---|---|
| 6 Experiments & CLI | `cli.py`, `experiments.py`, `benchmarks.py` | Build configs, run grids, compare results |
| 5 Configuration | `config.py`, `registry.py` | `SimulationConfig` (frozen, validated); registry maps enums → strategy classes |
| 4 Core | `simulation.py` | Tick loop; single entry point `run_simulation(requests, config)`; only code that mutates state |
| 3 Strategies | `dispatch/`, `movement/` | Pluggable. Dispatcher = which car; MovementPolicy = where next |
| 2 I/O | `elevator_requests.py`, `workloads.py`, `recorder.py`, `metrics.py`, `report.py` | Input loading + no-peek source, seeded workloads, positions log, stats |
| 1 Models | `models.py`, `physics.py` | `ElevatorRequest`, `Passenger`, `Elevator`, `ElevatorView`, `Direction`, `Action`; `physics.step` = one car's tick (stop: alight then board; or move) |

Boundaries:
- Core imports strategy interfaces only; concrete classes are wired in `registry.py`. The core gets its dispatcher from `registry.make_dispatcher(config)` and never names a concrete class. `run_simulation` also takes optional `dispatcher=` / `movement=` instances, used by benchmarks such as `dispatch/fixed.py`.
- Code lives in the `elevator_sim/` package; tests in `tests/`. Imports are absolute, from the module that defines the name.
- Strategies receive read-only `ElevatorView` snapshots. Only the simulation moves cars or boards passengers (a strategy's own internal counter, such as round robin's turn, is fine).
- Per-car rules live in `physics.step`. The simulation applies it to live state; the ETA dispatcher applies it to private copies rebuilt from views, so predictions and the real run share one set of physics.
- Recorder and metrics observe; they never change state.
- CLI runs, experiments and benchmarks all go through `run_simulation`, so every comparison uses the same physics and tick order.

Interfaces:

```python
class Dispatcher(Protocol):
    def assign(self, request: ElevatorRequest, elevators: Sequence[ElevatorView], t: int) -> int: ...

class MovementPolicy(Protocol):
    def next_action(self, elevator: ElevatorView) -> Action: ...  # UP | DOWN | STOP | IDLE
```

## Tick order

1. Ingest: `source.arrivals_at(t)`
2. Assign: `dispatcher.assign(...)` once per new passenger
3. Decide: `movement.next_action(...)` for every car
4. Apply: alight, board within capacity, or move one floor; stamp pickup and drop-off times
5. Record: one positions row
Then `t += 1`. Stop when the source is exhausted and everyone is delivered, or `t == max_ticks`.

## Config

`config.py` is a frozen pydantic model; `Field` bounds plus a model validator replace a hand-written `__post_init__`.

```python
class DispatchStrategy(StrEnum):
    ROUND_ROBIN = "round_robin"
    # ETA = "eta" added with step 2, so the enum never names an unregistered strategy

class SimulationConfig(BaseModel):  # frozen
    """Floors are 1-indexed: floor 1 is the lobby."""
    num_floors: int = 60            # >= 2 (a request needs two distinct floors)
    num_elevators: int = 4          # >= 1
    capacity: int = 12              # >= 1
    start_floor: int = 1            # where every car starts; 1 <= start_floor <= num_floors
    stop_duration: int = 1          # >= 1 ticks per stop (doors, boarding, alighting)
    dispatch: DispatchStrategy = DispatchStrategy.ROUND_ROBIN
    max_ticks: int = 100_000        # >= 1 safety cap
```

Not in config: output paths (the CLI writes the positions log from `result.positions`, so `run_simulation` does no file I/O), workload seed and traffic shape (`workloads.py`), the request data, per-strategy tuning (constructor args).
Requires Python 3.14+ (matches `pyproject.toml` and `.python-version`).

## Scope and build order

1. Core loop + round robin + LOOK, end to end on the sample input. Correct positions log and stats.
2. ETA cost dispatcher (headline): pick the elevator with the smallest marginal increase in total wait + travel for its passengers, by simulating that car's LOOK route with and without the new passenger. Optional knobs: weight wait over travel; fairness penalty on max wait.
3. Direction-aware nearest car (middle comparison).
4. Zone-based, if time allows; otherwise listed as future work.
Movement stays LOOK for every dispatcher comparison. SCAN is comparison-only.

## Benchmarks and metrics

- **Level 1 bound (all workloads):** private elevator waiting at each origin, so ideal total = |dest − source| + stop_duration (the alighting stop; boarding happens at request time). Sample input: 105 floors + 3 stops = 108 ticks at `stop_duration = 1`.
- **Level 2 bound (small workloads, ≤ ~12 passengers, 2–3 elevators):** offline-optimal dispatcher with perfect foresight under LOOK. Brute-force every assignment through `run_simulation` with `dispatch/fixed.py`. Bounds the best dispatcher under LOOK, not the best possible system.
- Round robin is a baseline, not an upper bound.
- `gap_closed = (round_robin − algo) / (round_robin − offline_optimal)`.
- Worst-case guarantee: LOOK reaches an assigned passenger within about `2 × (num_floors − 1)` ticks plus stop time (capacity can break this). Test it in `test_wait_bound.py`.
- No-peek applies to the algorithm under test, not to the benchmark.

## Design decisions

1. **Capacity vs. immediate assignment:** physics boards up to capacity, in arrival order. Passengers left behind keep their assigned car and stay a pickup target, so the car comes back for them. Assignment stays permanent and nobody starves (each car's passenger set is finite and LOOK always returns to an outstanding target). Reserving capacity at assignment is rejected as too conservative, because riders alight along the route. ETA accounts for capacity by simulating the route; round robin ignores it. `test_wait_bound.py` uses enough capacity that cars never fill.
2. **Direction rule at pickup:** at a stop, alight first, then LOOK sets the direction (continue if targets lie ahead, else reverse, else idle), then board waiting passengers whose direction matches. A car moving through floor f stops there for a drop-off, a same-direction pickup, or an opposite-direction pickup when f is the last target of the sweep (the turnaround).
3. **Same-tick ties:** stable sort by time, keeping input-file order within a tick (not by id: `passenger10` sorts before `passenger2`). Elevator ties go to the lowest index. Boarding under limited capacity is FIFO by request time, then file order.
4. **Input validation:** fail fast with an error naming the row for `source == dest`, floors outside `[1, num_floors]`, duplicate ids and negative times. Floor range is checked where the config is known (building the source), not in `ElevatorRequest`. Unsorted input is sorted by time; no-peek lives in `arrivals_at(t)`, not in file order. A stream could not sort, so it would need a late-arrival policy.
5. **Cross-zone trips:** deferred until zone dispatch exists. If built, zones are a dispatch preference only (every car reaches every floor); assign by the non-lobby endpoint's zone; a trip spanning two zones falls back to ETA across all cars.
6. **Stop cost:** a stop takes `stop_duration >= 1` ticks; a car never stops and moves in the same tick. Alighting and boarding at one floor share one stop.
7. **Timestamps:** pickup = the tick the passenger boards; drop-off = the tick they alight. Positions are recorded after Apply. A request at tick t can board at tick t (Ingest runs first). Example, sample passenger1 with an idle car at floor 1: board at t=0 (wait 0), move t=1–50, alight at t=51 (travel 51).

## Key tests

`test_elevator_requests.py` (no-peek), `test_look.py`, `test_capacity.py`, `test_wait_bound.py`, `test_metrics.py` (hand-computed sample input).

## Workloads

Seeded generators: morning rush (lobby up), evening rush (down to lobby), random inter-floor traffic, long idle gap.

## Time budget

Roughly 6–10 hours total, including the README. Time spent is logged and reported in the README.
