# Elevator Dispatch Simulator

A discrete-time simulation of a multi-elevator building using destination
dispatch, built to compare scheduling algorithms. The problem statement is in
[`docs/challenge.md`](docs/challenge.md); working design notes and recorded
trade-offs are in [`CLAUDE.md`](CLAUDE.md).

## Quick start

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python -m elevator_sim
```

With no options this runs a full office day (`data/office_day.csv`, 6,078
requests) in a 40-floor building with 8 elevators of capacity 16, compares
every dispatcher, and writes one positions log per dispatcher.

Run the sample input from the problem statement with one dispatcher:

```bash
uv run python -m elevator_sim --requests data/sample_requests.csv --floors 60 --elevators 4 --capacity 12 --dispatch etd
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--requests` | `data/office_day.csv` | CSV with header `time,id,source,dest` (also `ELEVATOR_REQUESTS_CSV`) |
| `--floors` | 40 | Floors, numbered 1..floors; floor 1 is the lobby |
| `--elevators` | 8 | Number of elevators |
| `--capacity` | 16 | Maximum passengers per elevator |
| `--start-floor` | 1 | Floor where every elevator starts |
| `--stop-duration` | 1 | Ticks per stop (doors, boarding, alighting) |
| `--dispatch` | all | `round_robin`, `nearest_car` or `etd`; repeat to pick several |
| `--max-ticks` | 100000 | Safety cap on simulation length |
| `--positions-log` | `elevator_positions.csv` | Positions CSV; with several dispatchers, one file each (`elevator_positions_<dispatcher>.csv`) |

Input that does not fit the settings is rejected before the run, with every
offending row and the value that would fit, for example
`num_floors must be at least 51`.

### Other commands

```bash
uv run python -m elevator_sim.experiments   # every dispatcher on every standard workload
uv run python -m elevator_sim.benchmarks    # dispatchers vs the offline optimum on small cases
uv run python -m elevator_sim.workloads     # regenerate data/office_day.csv
uv run pytest                               # test suite
```

## Output

1. **Elevator positions log:** one row per tick starting at `t=0`, with every
   elevator's floor: `time,e0,e1,...`
2. **Passenger statistics:** min, mean, p95 and max of
   - **wait**: request tick to pickup tick
   - **total time**: wait plus travel (pickup to drop-off)
   - **intermediate stops**: stops a rider sits through between boarding and alighting

   plus per-elevator utilization (single-dispatcher runs) and observations:
   time above the ideal, the share spent waiting, the wait tail and load
   balance. Comparison runs show the statistics side by side, mark the best
   value in each row, and summarize each dispatcher against round robin.

## How it works

**Time.** One tick is one floor of travel. The loop advances one tick at a
time, including idle stretches, and each tick runs:

1. **Ingest** requests whose time has come. The scheduler never sees a request
   before its time; this is enforced in one place, `RequestSource.arrivals_at(t)`.
2. **Assign** each new passenger to an elevator, permanently (destination dispatch).
3. **Decide** each elevator's action (move, stop or idle) with the LOOK movement policy.
4. **Apply** it: alight, then board up to capacity, or move one floor.
5. **Record** one positions row.

The run ends once every request has arrived and every passenger is delivered.

**Movement (LOOK).** A car keeps going in its direction while it has pickups or
drop-offs ahead, then reverses. It stops on a floor for a drop-off or for a
pickup going its way, and boards only passengers travelling in its direction
of departure. A car that is full ignores pickups until riders get off.

**Dispatchers**

| Dispatcher | How it assigns a request |
|---|---|
| Round robin | Cars take turns. Baseline. |
| Nearest car | The car that reaches the caller in the fewest floors, from its position, direction and the end of its current sweep. Ignores stops, load and delay to other passengers. |
| ETD (estimated time to destination) | For each car, simulate its LOOK route with and without the new passenger; pick the car whose passengers' summed wait plus ride time grows the least. Counts the delay a new passenger causes everyone already assigned, and full cars. |

ETD's predictions run the same per-car rules as the simulation
(`physics.step`), so a prediction made after a car's last assignment matches
the run tick for tick; a test checks this.

**Code layout** (`elevator_sim/`; each layer only calls the ones below it)

| Layer | Modules |
|---|---|
| CLI and experiments | `cli.py`, `experiments.py`, `benchmarks.py` |
| Configuration | `config.py`, `registry.py` |
| Core loop | `simulation.py` |
| Strategies | `dispatch/` (round robin, nearest car, ETD, fixed), `movement/look.py` |
| Input and output | `elevator_requests.py`, `workloads.py`, `recorder.py`, `metrics.py`, `report.py` |
| Models | `models.py`, `physics.py` |

## Assumptions

- **Boarding and timestamps.** A request at tick `t` can board at tick `t`.
  Pickup is the boarding tick and drop-off is the alighting tick. A stop takes
  `stop_duration` ticks, and a car never stops and moves in the same tick.
- **Capacity.** Cars board up to capacity in request order. Anyone left
  behind keeps their assigned car, which comes back for them, so assignments
  stay permanent and every passenger is eventually served.
- **Direction.** At a stop, riders alight first, the car then chooses its
  departure direction, and only passengers going that way board.
- **Ties.** Requests in the same tick keep their input-file order; elevator
  ties go to the lowest index.
- **Input.** Rows with `source == dest`, duplicate ids or negative times are
  rejected with the row number; unsorted input is sorted by time.
- **Ideal (private-car bound).** A car already waiting at each origin, so a
  passenger's ideal total is `distance + stop_duration`. It is unreachable once
  cars are shared and serves as a yardstick.
- **Office-day scale.** The bundled day assumes about 1.5 s per tick, so an
  hour is 2,400 ticks. Real door cycles are 8–10 s, about 6 ticks, so the
  default `--stop-duration 1` flatters every dispatcher.

## Results

### Office day (40 floors, 8 elevators, capacity 16, stop duration 1)

| Per trip | Round robin | Nearest car | ETD |
|---|---|---|---|
| Wait mean / p95 / max | 25.4 / 62 / 82 | 14.1 / 47 / 117 | **10.8 / 34 / 48** |
| Total mean / p95 / max | 44.3 / 89 / 119 | 34.5 / 77 / 152 | **30.7 / 68 / 88** |
| Stops mean / p95 / max | **0.6 / 3 / 6** | 2.1 / 8 / 14 | 1.6 / 7 / 15 |

ETD has the lowest wait and total time at every percentile. Nearest car gets
much of ETD's average gain but has the worst tail: it keeps sending callers to
whichever car is closest, which can strand someone behind a long sweep. Round
robin spreads riders thinly, so they share cars least and make the fewest
stops, but they wait far longer. ETD takes the extra stops into account
in its cost and still comes out ahead on total time.

### Every workload (`python -m elevator_sim.experiments`)

Mean wait, with max wait in brackets, in ticks:

| Workload | Round robin | Nearest car | ETD |
|---|---|---|---|
| Office day | 25.4 (82) | 14.1 (117) | **10.8 (48)** |
| Morning rush, 1,000 lobby-up trips in an hour | 33.5 (82) | 27.0 (178) | **19.0 (39)** |
| Evening rush, 1,000 trips down to the lobby | 31.6 (81) | 17.3 (82) | **12.5 (48)** |
| Between floors, 1,000 trips | 29.1 (86) | 7.2 (91) | **5.7 (49)** |
| Idle gap, two bursts with a long quiet stretch | 13.4 (43) | 5.3 (70) | **3.6 (29)** |

### Against the offline optimum (`python -m elevator_sim.benchmarks`)

Comparing with round robin only shows a dispatcher is not bad. On small cases
the best possible assignment can be computed exactly: it knows every request
in advance and tries every split of passengers among cars, under the same
physics and LOOK movement. Cars never interact, so an assignment's cost is the
sum of each car's cost on its own subset of passengers; simulating every
subset on one car and combining them by dynamic programming over subsets
makes the search exact, and tests confirm it against full brute force.

10 trips, 20 floors, 3 elevators, 100 random cases per row:

Ratios are total time ÷ optimum, mean (worst case). "Gap closed" is how much
of round robin's excess over the optimum a dispatcher removes.

| Scenario | Round robin | Nearest car | ETD | Gap closed: nearest car | Gap closed: ETD |
|---|---|---|---|---|---|
| Light (over 200 ticks) | 1.30 (1.67) | 1.10 (1.62) | **1.05 (1.24)** | 46% | **80%** |
| Burst (over 15 ticks) | 1.37 (1.98) | 1.19 (1.82) | **1.11 (1.53)** | 31% | **66%** |
| Burst, capacity 2 | 1.34 (1.77) | 1.31 (2.56) | **1.10 (1.56)** | −26% | **66%** |

ETD averages 5–11% above the best possible assignment. Part of the remaining
gap is the value of knowing future requests, which no real-time dispatcher can
recover. Nearest car falls behind round robin when cars fill up, because it
ignores load. A regression test keeps ETD within 12% of the optimum on fixed
cases.

## Testing

`uv run pytest` runs about 140 tests, including:

- the sample input hand-traced tick by tick
- the no-peek rule
- LOOK direction rules
- capacity and starvation
- a worst-case wait bound
- ETD predictions matching the run exactly
- the offline optimum against brute force

## Limitations and future work

- **Zone-based dispatch** was not built. A 40-floor building with one group of
  8 cars is where zoning would help most.
- **Express elevators** (skipping floors) were not built.
- **Fairness.** ETD minimizes summed time. A cost that grows faster with long
  waits, or a penalty past a wait threshold, would trade a little mean wait for
  a shorter tail. The benchmark already computes the fairness bound (the least
  possible max wait) to measure that.
- **Speed.** ETD simulates each car's route twice per request (about 10 s for
  the office day). Caching each car's cost without the new passenger would
  roughly halve that, and an event-driven clock that skips idle stretches
  would help long, sparse inputs.
- **Streaming input.** Requests come from a list. Swapping in a stream changes
  one class (`RequestSource`) but needs a policy for late or out-of-order
  arrivals, which a list can simply sort.
- **Movement.** Every comparison uses LOOK, so the offline optimum bounds
  dispatchers under LOOK, not the best possible system.

## Time spent

_TODO: hours spent, by phase._
