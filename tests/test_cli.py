from typer.testing import CliRunner

from elevator_sim.cli import DEFAULT_REQUESTS_PATH, SAMPLE_REQUESTS_PATH, app
from elevator_sim.config import DispatchStrategy
from tests.helpers import row

runner = CliRunner()
SAMPLE_ARGS = [
    "--requests",
    str(SAMPLE_REQUESTS_PATH),
    "--floors",
    "60",
    "--elevators",
    "4",
    "--capacity",
    "12",
]
SAMPLE_TITLE = (
    "sample_requests.csv: 3 passengers; 60 floors, 4 cars, capacity 12, stop duration 1"
)


def invoke(*args):
    result = runner.invoke(app, list(args))
    return result, result.output.splitlines()


def test_input_paths_exist():
    assert DEFAULT_REQUESTS_PATH.is_file()
    assert SAMPLE_REQUESTS_PATH.is_file()


def test_run_defaults_to_etd_and_writes_two_logs_and_a_chart(tmp_path):
    result, lines = invoke("run", *SAMPLE_ARGS, "--out", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert lines[0] == SAMPLE_TITLE and lines[2].split() == ["etd"]
    assert "  total max " in result.output and "  wait min " in result.output
    assert result.output.rstrip().endswith(f"files in {tmp_path}/")
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "passengers.csv",
        "positions.csv",
        "wait_by_hour.png",
    ]
    assert (tmp_path / "positions.csv").read_text().startswith("time,e0,e1,e2,e3\n")
    assert len((tmp_path / "passengers.csv").read_text().splitlines()) == 4


def test_run_takes_a_dispatcher(tmp_path):
    result, lines = invoke(
        "run", *SAMPLE_ARGS, "--dispatch", "round_robin", "--out", str(tmp_path)
    )
    assert result.exit_code == 0 and lines[2].split() == ["round_robin"]


def test_compare_writes_one_log_pair_per_dispatcher_and_one_chart(tmp_path):
    result, lines = invoke("compare", *SAMPLE_ARGS, "--out", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert lines[0] == SAMPLE_TITLE
    assert lines[2].split() == [s.value for s in DispatchStrategy]
    assert result.output.count("1. Serve every request") == 1
    for s in DispatchStrategy:
        assert (tmp_path / f"positions_{s.value}.csv").is_file()
        assert (tmp_path / f"passengers_{s.value}.csv").is_file()
    assert (tmp_path / "wait_by_hour.png").is_file()


def test_defaults_run_the_office_day(tmp_path):
    result, lines = invoke(
        "run", "--dispatch", "round_robin", "--out", str(tmp_path)
    )  # round robin: fast
    assert result.exit_code == 0, result.output
    assert (
        lines[0]
        == "office_day.csv: 6078 passengers; 40 floors, 8 cars, capacity 16, stop duration 1"
    )


def test_run_cut_short_renders_dashes(tmp_path):
    # The last request is at t=10, so 11 is the smallest cap the input allows;
    # nobody reaches a destination before the run stops.
    result, _ = invoke(
        "run",
        *SAMPLE_ARGS,
        "--dispatch",
        "round_robin",
        "--max-ticks",
        "11",
        "--out",
        str(tmp_path),
    )
    assert result.exit_code == 0, result.output
    assert row(result.output, "delivered").split()[-1] == "0"
    assert row(result.output, "wait mean").split()[-1] == "-"
    assert (tmp_path / "wait_by_hour.png").is_file()


def test_etd_with_a_cap_shorter_than_its_routes_is_a_clean_error(tmp_path):
    # ETD predicts whole routes and max_ticks is its horizon.
    result, _ = invoke("run", *SAMPLE_ARGS, "--max-ticks", "11", "--out", str(tmp_path))
    assert result.exit_code == 1
    assert "error: route for elevator 0 exceeds 11 ticks" in result.output


def test_out_directory_is_created(tmp_path):
    out = tmp_path / "a" / "b"
    result, _ = invoke("run", *SAMPLE_ARGS, "--out", str(out))
    assert result.exit_code == 0 and (out / "positions.csv").is_file()


def test_benchmark_prints_three_tables_and_writes_the_chart(tmp_path):
    result, _ = invoke("benchmark", "--seeds", "1", "--out", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert result.output.count("total / optimum, mean") == 3
    assert "mean of 1 seeds" in result.output
    assert (tmp_path / "benchmark.png").is_file()


def test_benchmark_rejects_zero_seeds(tmp_path):
    result, _ = invoke("benchmark", "--seeds", "0", "--out", str(tmp_path))
    assert result.exit_code == 2


def test_input_that_does_not_fit_the_building_exits_with_error(tmp_path):
    result, _ = invoke(
        "run",
        "--requests",
        str(SAMPLE_REQUESTS_PATH),
        "--floors",
        "40",
        "--out",
        str(tmp_path),
    )
    assert result.exit_code == 1 and "num_floors must be at least 51" in result.output


def test_invalid_config_exits_with_error(tmp_path):
    result, _ = invoke("run", "--stop-duration", "0", "--out", str(tmp_path))
    assert result.exit_code == 1 and "stop_duration" in result.output


def test_no_command_prints_help():
    result, _ = invoke()
    assert "Usage" in result.output


def test_unwritable_out_is_a_clean_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    result, _ = invoke("run", *SAMPLE_ARGS, "--out", str(blocker / "sub"))
    assert result.exit_code == 1
    assert "error:" in result.output
