from pathlib import Path
from typing import Annotated

import typer

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.elevator_requests import load_requests_csv
from elevator_sim.experiments import compare
from elevator_sim.report import format_comparison, format_report
from elevator_sim.workloads import DEFAULT_OFFICE_DAY, OFFICE_DAY_PATH

# Relative to the working directory (the repo root when run as documented).
# Override with --requests or the ELEVATOR_REQUESTS_CSV environment variable.
DEFAULT_REQUESTS_PATH = OFFICE_DAY_PATH
SAMPLE_REQUESTS_PATH = Path("data/sample_requests.csv")
DEFAULT_POSITIONS_LOG_PATH = Path("elevator_positions.csv")

# Defaults match the office day: its building, and a fleet sized for its peaks.
OFFICE_DAY_ELEVATORS = 8
OFFICE_DAY_CAPACITY = 16
_DEFAULTS = SimulationConfig(
    num_floors=DEFAULT_OFFICE_DAY.num_floors,
    num_elevators=OFFICE_DAY_ELEVATORS,
    capacity=OFFICE_DAY_CAPACITY,
)

app = typer.Typer(
    add_completion=False,
    help="Run an elevator dispatch simulation, or compare dispatchers.",
)


@app.command()
def run(
    requests: Annotated[
        Path,
        typer.Option(
            envvar="ELEVATOR_REQUESTS_CSV",
            exists=True,
            dir_okay=False,
            help="CSV with header time,id,source,dest.",
        ),
    ] = DEFAULT_REQUESTS_PATH,
    floors: int = _DEFAULTS.num_floors,
    elevators: int = _DEFAULTS.num_elevators,
    capacity: int = _DEFAULTS.capacity,
    start_floor: int = _DEFAULTS.start_floor,
    stop_duration: int = _DEFAULTS.stop_duration,
    dispatch: Annotated[
        list[DispatchStrategy] | None,
        typer.Option(help="Repeat to choose several. Default: run and compare all."),
    ] = None,
    max_ticks: int = _DEFAULTS.max_ticks,
    positions_log: Annotated[
        Path,
        typer.Option(dir_okay=False, help="Where to write the per-tick positions CSV."),
    ] = DEFAULT_POSITIONS_LOG_PATH,
) -> None:
    strategies = list(dict.fromkeys(dispatch or DispatchStrategy))  # dedupe, keep order
    try:
        config = SimulationConfig(
            num_floors=floors,
            num_elevators=elevators,
            capacity=capacity,
            start_floor=start_floor,
            stop_duration=stop_duration,
            dispatch=strategies[0],
            max_ticks=max_ticks,
        )
        runs = compare(load_requests_csv(requests), config, strategies)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    if len(runs) == 1:
        run = runs[0]
        run.result.positions.write_csv(positions_log)
        typer.echo(format_report(run.metrics))
        typer.echo(f"\nPositions log: {positions_log}")
        return

    typer.echo(
        format_comparison(
            [(r.strategy.value, r.metrics) for r in runs], [r.seconds for r in runs]
        )
    )
    typer.echo("\nPositions logs:")
    for r in runs:
        path = positions_log.with_stem(f"{positions_log.stem}_{r.strategy.value}")
        r.result.positions.write_csv(path)
        typer.echo(f"  {r.strategy.value}: {path}")


def main() -> None:
    app()
