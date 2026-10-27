from typer.testing import CliRunner

from elevator_sim.cli import DEFAULT_REQUESTS_PATH, SAMPLE_REQUESTS_PATH, app
from elevator_sim.config import DispatchStrategy

runner = CliRunner()
SAMPLE_BUILDING = [
    "--requests",
    str(SAMPLE_REQUESTS_PATH),
    "--floors",
    "60",
    "--elevators",
    "4",
]


def test_input_paths_exist():
    assert DEFAULT_REQUESTS_PATH.is_file()
    assert SAMPLE_REQUESTS_PATH.is_file()


def test_defaults_run_the_office_day(tmp_path):
    # Round robin only: comparing every dispatcher on the full day is slow for a test.
    args = [
        "--dispatch",
        "round_robin",
        "--positions-log",
        str(tmp_path / "positions.csv"),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "6078/6078 delivered" in result.output


def test_runs_and_writes_positions_log(tmp_path):
    log = tmp_path / "positions.csv"
    args = [*SAMPLE_BUILDING, "--dispatch", "etd", "--positions-log", str(log)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "3/3 delivered in 52 ticks" in result.output
    assert log.read_text().startswith("time,e0,e1,e2,e3\n")


def test_without_dispatch_compares_every_strategy(tmp_path):
    log = tmp_path / "positions.csv"
    result = runner.invoke(app, [*SAMPLE_BUILDING, "--positions-log", str(log)])
    assert result.exit_code == 0, result.output
    assert "Dispatch comparison (3 passengers)" in result.output
    for strategy in DispatchStrategy:
        assert strategy.value in result.output
        assert (tmp_path / f"positions_{strategy.value}.csv").is_file()
    assert not log.exists()


def test_input_that_does_not_fit_the_building_exits_with_error(tmp_path):
    args = ["--requests", str(SAMPLE_REQUESTS_PATH), "--floors", "40"]
    result = runner.invoke(app, [*args, "--positions-log", str(tmp_path / "p.csv")])
    assert result.exit_code == 1
    assert "num_floors must be at least 51" in result.output


def test_invalid_config_exits_with_error(tmp_path):
    result = runner.invoke(
        app, ["--stop-duration", "0", "--positions-log", str(tmp_path / "p.csv")]
    )
    assert result.exit_code == 1
    assert "stop_duration" in result.output
