"""One table for every command.

Rows are grouped under the three objectives of the problem statement (serve
every request; minimize total time per passenger; honor the capacity and
direction constraints), plus a Fleet line. `run` prints one column,
`compare` one per dispatcher, and `benchmark` the averages over seeds with
the optimum as a reference column. `*` marks the best dispatcher in a ranked
row when the columns differ.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from elevator_sim.metrics import Distribution, RunMetrics

OBJECTIVE_SERVE = "1. Serve every request"
OBJECTIVE_TIME = "2. Minimize total time"
OBJECTIVE_CONSTRAINTS = "3. Honor capacity and direction"
FLEET = "Fleet"


def constraints_held(m: RunMetrics) -> bool:
    """Capacity never exceeded and no rider carried away from their destination."""
    return m.max_load <= m.capacity and m.wrong_way_floors == 0


Cell = float | str | None


@dataclass(frozen=True, slots=True)
class Row:
    """One line of the table: where it sits, what it shows, how it ranks."""

    section: str
    label: str
    fmt: str  # format spec; "s" for text
    lower: bool | None  # True: lower is better; False: higher is; None: not ranked
    get: Callable[[RunMetrics], Cell] | None = None  # None for rows a caller fills


def _stat(d: Distribution | None, stat: str) -> float | None:
    return None if d is None else getattr(d, stat)


SECTIONS: tuple[str, ...] = (
    OBJECTIVE_SERVE,
    OBJECTIVE_TIME,
    OBJECTIVE_CONSTRAINTS,
    FLEET,
)

# The minima are reported, not ranked: the shortest wait in a run says
# nothing about the dispatcher.
ROWS: tuple[Row, ...] = (
    Row(OBJECTIVE_SERVE, "delivered", "d", False, lambda m: m.delivered),
    Row(OBJECTIVE_SERVE, "wait max", ".0f", True, lambda m: _stat(m.wait, "max")),
    Row(OBJECTIVE_SERVE, "total max", ".0f", True, lambda m: _stat(m.total, "max")),
    Row(
        OBJECTIVE_SERVE,
        "left behind, most",
        "d",
        True,
        lambda m: m.most_left_behind[1] if m.most_left_behind else 0,
    ),
    Row(OBJECTIVE_TIME, "wait min", ".0f", None, lambda m: _stat(m.wait, "min")),
    Row(OBJECTIVE_TIME, "wait mean", ".1f", True, lambda m: _stat(m.wait, "mean")),
    Row(OBJECTIVE_TIME, "wait p95", ".0f", True, lambda m: _stat(m.wait, "p95")),
    Row(OBJECTIVE_TIME, "total min", ".0f", None, lambda m: _stat(m.total, "min")),
    Row(OBJECTIVE_TIME, "total mean", ".1f", True, lambda m: _stat(m.total, "mean")),
    Row(OBJECTIVE_TIME, "total p95", ".0f", True, lambda m: _stat(m.total, "p95")),
    Row(OBJECTIVE_TIME, "stops mean", ".1f", True, lambda m: _stat(m.stops, "mean")),
    Row(
        OBJECTIVE_CONSTRAINTS,
        "constraints",
        "s",
        None,
        lambda m: "held" if constraints_held(m) else "VIOLATED",
    ),
    Row(OBJECTIVE_CONSTRAINTS, "max load", "d", None, lambda m: m.max_load),
    Row(OBJECTIVE_CONSTRAINTS, "full car-ticks", "d", True, lambda m: m.full_ticks),
    Row(OBJECTIVE_CONSTRAINTS, "left behind", "d", True, lambda m: m.left_behind),
    Row(FLEET, "deadhead", ".0%", True, lambda m: m.deadhead),
)


def values(m: RunMetrics) -> dict[str, Cell]:
    """One cell per row of ROWS, keyed by label."""
    return {r.label: r.get(m) for r in ROWS if r.get is not None}


def mean_values(samples: Sequence[Mapping[str, Cell]]) -> dict[str, Cell]:
    """Average the samples label by label: the mean of the numbers present
    (None if there are none); a text cell is "held" only if every sample
    says so."""
    labels = dict.fromkeys(label for sample in samples for label in sample)
    out: dict[str, Cell] = {}
    for label in labels:
        cells = [sample.get(label) for sample in samples]
        texts = [c for c in cells if isinstance(c, str)]
        numbers = [
            c for c in cells if isinstance(c, int | float) and not isinstance(c, bool)
        ]
        if texts:
            out[label] = "held" if all(t == "held" for t in texts) else "VIOLATED"
        else:
            out[label] = sum(numbers) / len(numbers) if numbers else None
    return out


def format_table(
    title: str,
    columns: Sequence[tuple[str, Mapping[str, Cell]]],
    rows: Sequence[Row] = ROWS,
    reference: tuple[str, Mapping[str, Cell]] | None = None,
) -> str:
    """The title, then one column per run with the rows grouped by section.
    `*` marks the best column in a ranked row when the columns differ; `-`
    is a missing value. `reference` is drawn last and never ranked."""
    names = [name for name, _ in columns]
    if reference is not None:
        names.append(reference[0])
    width = max(12, *(len(n) + 2 for n in names))
    label_width = max(len(r.label) for r in rows) + 4
    lines = [title, "", " " * label_width + "".join(f"{n:>{width}}" for n in names)]
    for section in SECTIONS:
        section_rows = [r for r in rows if r.section == section]
        if not section_rows:
            continue
        lines.append(section)
        for r in section_rows:
            cells = [m.get(r.label) for _, m in columns]
            line = _render_row(
                f"  {r.label}", cells, r.fmt, r.lower, label_width, width
            )
            if reference is not None:
                line += f"{_cell(reference[1].get(r.label), r.fmt) + ' ':>{width}}"
            lines.append(line)
    return "\n".join(lines)


def _cell(value: Cell, fmt: str) -> str:
    return (
        "-"
        if value is None
        else value
        if isinstance(value, str)
        else format(value, fmt)
    )


def _render_row(
    label: str,
    values: list,
    fmt: str,
    lower: bool | None,
    label_width: int,
    width: int,
) -> str:
    texts = [_cell(v, fmt) for v in values]
    best = _best(values, texts, lower)
    cells = [f"{t + ('*' if t == best else ' '):>{width}}" for t in texts]
    return f"{label:<{label_width}}" + "".join(cells)


def _best(values: list, texts: list[str], lower: bool | None) -> str | None:
    """The displayed text of the best value, or None when the row has no
    better direction or every run shows the same value."""
    shown = {t for v, t in zip(values, texts, strict=True) if v is not None}
    if lower is None or len(shown) < 2:
        return None
    pick = min if lower else max
    return texts[values.index(pick(v for v in values if v is not None))]
