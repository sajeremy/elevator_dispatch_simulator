import argparse
from pathlib import Path

from .config import DispatchStrategy, SimulationConfig
from .metrics import compute_metrics
from .report import format_report
from .requests import load_requests_csv
from .simulation import run_simulation

DEFAULT_REQUESTS = Path(__file__).resolve().parent.parent / "data" / "sample_requests.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = SimulationConfig()
    p = argparse.ArgumentParser(description="Run an elevator dispatch simulation.")
    p.add_argument(
        "requests",
        nargs="?",
        default=DEFAULT_REQUESTS,
        type=Path,
        help="CSV with header time,id,source,dest (default: the sample input)",
    )
    p.add_argument("--floors", type=int, default=defaults.num_floors)
    p.add_argument("--elevators", type=int, default=defaults.num_elevators)
    p.add_argument("--capacity", type=int, default=defaults.capacity)
    p.add_argument("--start-floor", type=int, default=defaults.start_floor)
    p.add_argument("--stop-duration", type=int, default=defaults.stop_duration)
    p.add_argument(
        "--dispatch",
        choices=[s.value for s in DispatchStrategy],
        default=defaults.dispatch.value,
    )
    p.add_argument("--max-ticks", type=int, default=defaults.max_ticks)
    p.add_argument("--positions-log", default=defaults.positions_log_path)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        config = SimulationConfig(
            num_floors=args.floors,
            num_elevators=args.elevators,
            capacity=args.capacity,
            start_floor=args.start_floor,
            stop_duration=args.stop_duration,
            dispatch=DispatchStrategy(args.dispatch),
            max_ticks=args.max_ticks,
            positions_log_path=args.positions_log,
        )
        result = run_simulation(load_requests_csv(args.requests), config)
    except ValueError as e:
        raise SystemExit(f"error: {e}") from e
    print(format_report(compute_metrics(result)))
    print(f"\nPositions log: {config.positions_log_path}")
