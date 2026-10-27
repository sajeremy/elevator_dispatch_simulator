"""The table answers the problem statement's three objectives: its rows are
grouped by the objective they measure (serve every request, minimize total
time, honor the constraints), plus a Fleet line."""

from dataclasses import replace

from elevator_sim.config import DispatchStrategy
from elevator_sim.metrics import compute_metrics
from elevator_sim.report import ROWS, format_table, mean_values, values
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE, SAMPLE_BUILDING, column, row

OBJECTIVES = (
    "1. Serve every request",
    "2. Minimize total time",
    "3. Honor capacity and direction",
)


def metrics(strategy=DispatchStrategy.ROUND_ROBIN):
    return compute_metrics(
        run_simulation(
            SAMPLE, SAMPLE_BUILDING.model_copy(update={"dispatch": strategy})
        )
    )


def in_order(text: str, parts) -> bool:
    positions = [text.find(p) for p in parts]
    return all(p >= 0 for p in positions) and positions == sorted(positions)


def test_values_has_one_cell_per_row_in_order():
    v = values(metrics())
    assert list(v) == [r.label for r in ROWS]
    assert (v["delivered"], v["wait max"], v["total max"]) == (3, 19, 51)
    assert (v["wait min"], v["total min"], v["constraints"]) == (0, 37, "held")
    assert values(replace(metrics(), wrong_way_floors=2))["constraints"] == "VIOLATED"


def test_table_layout_title_columns_sections_rows():
    text = format_table("sample", [("round_robin", values(metrics()))])
    lines = text.splitlines()
    assert (
        lines[0] == "sample" and lines[1] == "" and lines[2].split() == ["round_robin"]
    )
    assert in_order(text, (*OBJECTIVES, "Fleet"))
    for r in ROWS:
        assert f"  {r.label} " in text, r.label
    assert "above ideal" not in text and "*" not in text  # one column: nothing to rank


def test_star_marks_the_best_cell_and_skips_ties_and_unranked_rows():
    a = column(
        **{
            "wait max": 10,
            "wait mean": 4.0,
            "delivered": 3,
            "max load": 2,
            "wait min": 0,
        }
    )
    b = column(
        **{
            "wait max": 8,
            "wait mean": 4.0,
            "delivered": 3,
            "max load": 1,
            "wait min": 1,
        }
    )
    text = format_table("t", [("a", a), ("b", b)])
    assert row(text, "wait max").rstrip().endswith("8*")
    assert "*" not in row(text, "wait mean")  # tie
    assert "*" not in row(text, "max load")  # not ranked
    assert "*" not in row(text, "wait min")  # reported, not ranked
    assert row(text, "stops mean").split()[-2:] == ["-", "-"]  # missing values


def test_reference_column_is_last_and_never_starred():
    a, b = column(**{"total mean": 30.0}), column(**{"total mean": 25.0})
    opt = column(**{"total mean": 20.0})
    text = format_table("t", [("a", a), ("b", b)], reference=("optimum", opt))
    assert text.splitlines()[2].split() == ["a", "b", "optimum"]
    cells = row(text, "total mean").split()
    assert cells[-3:] == ["30.0", "25.0*", "20.0"]


def test_missing_label_renders_a_dash():
    text = format_table("t", [("a", {"wait max": 5})])  # every other label absent
    assert row(text, "total mean").split()[-1] == "-"


def test_mean_values_averages_numbers_and_ands_the_constraints():
    a = column(**{"wait mean": 2.0, "delivered": 10, "constraints": "held"})
    b = column(**{"wait mean": 4.0, "delivered": 8, "constraints": "VIOLATED"})
    m = mean_values([a, b])
    assert (m["wait mean"], m["delivered"], m["constraints"]) == (3.0, 9.0, "VIOLATED")
    assert m["stops mean"] is None
    assert mean_values([a, a])["constraints"] == "held"


def test_mean_values_skips_missing_samples():
    a, b = column(deadhead=0.5), column(deadhead=None)
    assert mean_values([a, b])["deadhead"] == 0.5
