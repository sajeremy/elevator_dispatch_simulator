from pathlib import Path
from typing import Annotated

import typer

from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.elevator_requests import load_requests_csv
from elevator_sim.metrics import compute_metrics
from elevator_sim.report import format_report
from elevator_sim.simulation import run_simulation

# Relative to the working directory (the repo root when run as documented).
# Override with the argument or the ELEVATOR_REQUESTS_CSV environment variable.
DEFAULT_REQUESTS_PATH = Path("data/sample_requests.csv")
DEFAULT_POSITIONS_LOG_PATH = Path("elevator_positions.csv")

_DEFAULTS = SimulationConfig()

app = typer.Typer(add_completion=False, help="Run an elevator dispatch simulation.")


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
    dispatch: DispatchStrategy = _DEFAULTS.dispatch,
    max_ticks: int = _DEFAULTS.max_ticks,
    positions_log: Annotated[
        Path, typer.Option(dir_okay=False, help="Where to write the per-tick positions CSV.")
    ] = DEFAULT_POSITIONS_LOG_PATH,
) -> None:
    try:
        config = SimulationConfig(
            num_floors=floors,
            num_elevators=elevators,
            capacity=capacity,
            start_floor=start_floor,
            stop_duration=stop_duration,
            dispatch=dispatch,
            max_ticks=max_ticks,
        )
        result = run_simulation(load_requests_csv(requests), config)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    result.positions.write_csv(positions_log)
    typer.echo(format_report(compute_metrics(result)))
    typer.echo(f"\nPositions log: {positions_log}")


def main() -> None:
    app()
