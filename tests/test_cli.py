from typer.testing import CliRunner

from elevator_sim.cli import DEFAULT_REQUESTS_PATH, app

runner = CliRunner()


def test_default_path_points_at_the_sample_input():
    assert DEFAULT_REQUESTS_PATH.is_file()


def test_runs_and_writes_positions_log(tmp_path):
    log = tmp_path / "positions.csv"
    result = runner.invoke(
        app, ["--requests", str(DEFAULT_REQUESTS_PATH), "--positions-log", str(log)]
    )
    assert result.exit_code == 0, result.output
    assert "3/3 delivered in 52 ticks" in result.output
    assert log.read_text().startswith("time,e0,e1,e2,e3\n")


def test_invalid_config_exits_with_error(tmp_path):
    result = runner.invoke(
        app, ["--stop-duration", "0", "--positions-log", str(tmp_path / "p.csv")]
    )
    assert result.exit_code == 1
    assert "stop_duration" in result.output
