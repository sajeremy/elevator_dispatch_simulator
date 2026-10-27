"""Command line: run one dispatcher, compare them all, or benchmark them
against the offline optimum.

Every command prints the same table (rows grouped under the three
objectives, one column per dispatcher) and writes its logs and one chart to
`--out`. The building options default to the office day's building.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from elevator_sim import experiments
from elevator_sim.benchmarks import TINY_SCENARIOS, format_suite, ratios, run_suite
from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.elevator_requests import load_requests_csv
from elevator_sim.recorder import write_passengers_csv
from elevator_sim.report import format_table, values
from elevator_sim.viz import benchmark_ratios, wait_by_hour
from elevator_sim.workloads import OFFICE_DAY_PATH

DEFAULTS = SimulationConfig()
# Relative to the working directory (the repo root when run as documented).
# Override with --requests or the ELEVATOR_REQUESTS_CSV environment variable.
DEFAULT_REQUESTS_PATH = OFFICE_DAY_PATH
SAMPLE_REQUESTS_PATH = Path("data/sample_requests.csv")
DEFAULT_OUT = Path("results")

Requests = Annotated[
    Path,
    typer.Option(
        envvar="ELEVATOR_REQUESTS_CSV",
        exists=True,
        dir_okay=False,
        help="CSV with header time,id,source,dest.",
    ),
]
Floors = Annotated[
    int, typer.Option(help="Floors in the building, numbered 1..floors.")
]
Elevators = Annotated[int, typer.Option(help="Number of elevators.")]
Capacity = Annotated[int, typer.Option(help="Maximum passengers per elevator.")]
StartFloor = Annotated[int, typer.Option(help="Floor where every elevator starts.")]
StopDuration = Annotated[
    int, typer.Option(help="Ticks per stop (doors, boarding, alighting).")
]
MaxTicks = Annotated[int, typer.Option(help="Safety cap on simulation length.")]
Out = Annotated[
    Path, typer.Option(file_okay=False, help="Directory for the logs and the chart.")
]

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "Elevator dispatch simulator: run one dispatcher, compare them all, "
        "or benchmark them against the offline optimum."
    ),
)


@app.command()
def run(
    requests: Requests = DEFAULT_REQUESTS_PATH,
    dispatch: Annotated[
        DispatchStrategy, typer.Option(help="Dispatcher to run.")
    ] = DEFAULTS.dispatch,
    floors: Floors = DEFAULTS.num_floors,
    elevators: Elevators = DEFAULTS.num_elevators,
    capacity: Capacity = DEFAULTS.capacity,
    start_floor: StartFloor = DEFAULTS.start_floor,
    stop_duration: StopDuration = DEFAULTS.stop_duration,
    max_ticks: MaxTicks = DEFAULTS.max_ticks,
    out: Out = DEFAULT_OUT,
) -> None:
    """Run one dispatcher (ETD by default) and print its table."""
    _simulate(requests, [dispatch], _building(locals()), out)


@app.command()
def compare(
    requests: Requests = DEFAULT_REQUESTS_PATH,
    floors: Floors = DEFAULTS.num_floors,
    elevators: Elevators = DEFAULTS.num_elevators,
    capacity: Capacity = DEFAULTS.capacity,
    start_floor: StartFloor = DEFAULTS.start_floor,
    stop_duration: StopDuration = DEFAULTS.stop_duration,
    max_ticks: MaxTicks = DEFAULTS.max_ticks,
    out: Out = DEFAULT_OUT,
) -> None:
    """Run every dispatcher on the same input and print them side by side."""
    _simulate(requests, list(DispatchStrategy), _building(locals()), out)


@app.command()
def benchmark(
    seeds: Annotated[int, typer.Option(min=1, help="Random cases per scenario.")] = 100,
    out: Out = DEFAULT_OUT,
) -> None:
    """Compare the dispatchers with the offline optimum on tiny cases."""
    try:
        out.mkdir(parents=True, exist_ok=True)  # fail before the run, not after
    except OSError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    tables, chart = [], []
    for scenario in TINY_SCENARIOS:
        cases = run_suite(scenario, range(seeds))
        tables.append(format_suite(scenario, cases))
        chart.append((scenario.name, ratios(cases)))
    benchmark_ratios(chart, out / "benchmark.png")
    typer.echo("\n\n".join(tables))
    typer.echo(f"\nfiles in {out}/")


def _building(options: dict) -> dict[str, int]:
    """The SimulationConfig fields among a command's options."""
    names = {
        "floors": "num_floors",
        "elevators": "num_elevators",
        "capacity": "capacity",
        "start_floor": "start_floor",
        "stop_duration": "stop_duration",
        "max_ticks": "max_ticks",
    }
    return {field: options[option] for option, field in names.items()}


def _simulate(
    requests_path: Path,
    strategies: Sequence[DispatchStrategy],
    building: dict[str, int],
    out: Path,
) -> None:
    try:
        config = SimulationConfig(**building, dispatch=strategies[0])
        requests = load_requests_csv(requests_path)
        out.mkdir(parents=True, exist_ok=True)  # fail before the run, not after
        runs = experiments.compare(requests, config, strategies)
    except (ValueError, OSError) as e:  # bad config or input; unwritable --out
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    for r in runs:
        suffix = f"_{r.strategy.value}" if len(runs) > 1 else ""
        r.result.positions.write_csv(out / f"positions{suffix}.csv")
        write_passengers_csv(r.result.passengers, out / f"passengers{suffix}.csv")
    wait_by_hour(
        [(r.strategy.value, r.result.passengers) for r in runs],
        out / "wait_by_hour.png",
    )
    title = (
        f"{requests_path.name}: {len(requests)} passengers; "
        f"{config.num_floors} floors, {config.num_elevators} cars, "
        f"capacity {config.capacity}, stop duration {config.stop_duration}"
    )
    typer.echo(
        format_table(title, [(r.strategy.value, values(r.metrics)) for r in runs])
    )
    typer.echo(f"\nfiles in {out}/")


def main() -> None:
    app()
