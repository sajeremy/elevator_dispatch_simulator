"""Plain-text summary of a run's metrics, and a side-by-side comparison of runs."""

from collections.abc import Mapping, Sequence

from elevator_sim.metrics import Distribution, RunMetrics


def _row(name: str, d: Distribution | None, fmt: str = ".0f") -> str:
    if d is None:
        return f"  {name:<8} (no delivered passengers)"
    return (
        f"  {name:<8} min {d.min:>7{fmt}}  mean {d.mean:>7.2f}  "
        f"p95 {d.p95:>7{fmt}}  max {d.max:>7{fmt}}"
    )


def observations(m: RunMetrics) -> list[str]:
    notes: list[str] = []
    if not m.completed:
        notes.append(
            f"Run hit max_ticks: {m.passengers - m.delivered} of {m.passengers} "
            "passengers were not delivered and are excluded from the statistics."
        )
    if m.total and m.ideal_total_sum:
        overhead = m.total_time_sum / m.ideal_total_sum - 1
        notes.append(
            f"Total time is {overhead:.0%} above the private-car bound "
            f"({m.total_time_sum} vs {m.ideal_total_sum} ticks)."
        )
    if m.wait and m.total and m.total_time_sum:
        share = m.wait.mean * m.wait.count / m.total_time_sum
        notes.append(f"Waiting is {share:.0%} of passenger time; riding is the rest.")
    if m.wait and m.wait.mean > 0:
        notes.append(
            f"Wait tail: p95 is {m.wait.p95 / m.wait.mean:.1f}x the mean; "
            f"longest wait {m.longest_wait[1]} ticks ({m.longest_wait[0]})."
        )
    if len(m.elevators) > 1:
        busiest = max(m.elevators, key=lambda e: e.utilization)
        idlest = min(m.elevators, key=lambda e: e.utilization)
        notes.append(
            f"Load balance: e{busiest.index} busy {busiest.utilization:.0%} of ticks, "
            f"e{idlest.index} {idlest.utilization:.0%}."
        )
    if m.elevators:
        full = f"full for {m.full_ticks} car-ticks" if m.full_ticks else "never full"
        if m.most_left_behind:
            who, times = m.most_left_behind
            left = f"{m.left_behind} departures left a passenger behind (most: {who}, {times}x)"
        else:
            left = "nobody left behind"
        notes.append(f"Capacity: max load {m.max_load}; cars {full}; {left}.")
    if m.deadhead is not None:
        notes.append(f"Deadheading: {m.deadhead:.0%} of moving ticks carry nobody.")
    return notes


def format_report(m: RunMetrics) -> str:
    lines = [
        f"Passengers: {m.delivered}/{m.passengers} delivered in {m.ticks} ticks",
        "",
        "Per trip (wait and total in ticks; stops = intermediate stops)",
        _row("wait", m.wait),
        _row("total", m.total),
        _row("stops", m.stops),
        "",
        "Elevators",
    ]
    for e in m.elevators:
        lines.append(
            f"  e{e.index}  served {e.passengers_served:>4}  busy {e.utilization:>4.0%}  "
            f"(moving {e.moving_ticks}, stopped {e.stopped_ticks}, idle {e.idle_ticks})"
            f"  max load {e.max_load}"
        )
    notes = observations(m)
    if notes:
        lines += ["", "Observations"] + [f"  - {n}" for n in notes]
    return "\n".join(lines)


def _distribution_rows(name: str, attr: str) -> list[tuple]:
    """min, mean, p95, max; only the mean can be fractional."""
    return [
        (
            f"{name} {stat}",
            lambda m, s=stat: _stat(getattr(m, attr), s),
            ".1f" if stat == "mean" else ".0f",
            True,
        )
        for stat in ("min", "mean", "p95", "max")
    ]


def _stat(d: Distribution | None, stat: str) -> float | None:
    return None if d is None else getattr(d, stat)


# (label, value from a run's metrics, number format, whether lower is better;
# None when the row has no better direction).
_COMPARISON_ROWS = [
    ("delivered", lambda m: m.delivered, "d", False),
    *_distribution_rows("wait", "wait"),
    *_distribution_rows("total", "total"),
    *_distribution_rows("stops", "stops"),
    ("max load", lambda m: m.max_load, "d", None),
    ("full car-ticks", lambda m: m.full_ticks, "d", True),
    ("left behind", lambda m: m.left_behind, "d", True),
    ("deadhead", lambda m: m.deadhead, ".0%", True),
]

# Headline rows for the summary against the first column.
_HEADLINES = ("wait mean", "wait p95", "wait max", "total mean", "stops mean")


def format_comparison(runs: Sequence[tuple[str, RunMetrics]]) -> str:
    """Metrics side by side, one column per run. `*` marks the best value in
    a row when the runs differ. The summary compares each run with the first
    one."""
    names = [name for name, _ in runs]
    width = max(12, *(len(n) + 2 for n in names))
    label_width = max(len(label) for label, *_ in _COMPARISON_ROWS) + 2
    rows = [
        (label, [get(m) for _, m in runs], fmt, lower)
        for label, get, fmt, lower in _COMPARISON_ROWS
    ]
    lines = [
        f"Dispatch comparison ({runs[0][1].passengers} passengers)",
        "",
        " " * label_width + "".join(f"{n:>{width}}" for n in names),
    ]
    lines += [_render_row(*row, label_width, width) for row in rows]

    if len(runs) > 1:
        base_name = names[0]
        by_label = {label: values for label, values, *_ in rows}
        lines += ["", f"Versus {base_name}"]
        for i, name in enumerate(names[1:], start=1):
            parts = []
            for label in _HEADLINES:
                before, after = by_label[label][0], by_label[label][i]
                if before and after is not None:
                    parts.append(f"{label} {after / before - 1:+.0%}")
            lines.append(f"  {name}: " + ", ".join(parts))
    return "\n".join(lines)


def format_grid(grid: Mapping[str, Sequence[tuple[str, RunMetrics]]]) -> str:
    """One block per workload with the same rows as `format_comparison`, one
    column per run. `*` marks the best value in each row."""
    names = [name for name, _ in next(iter(grid.values()))]
    width = max(12, *(len(n) + 2 for n in names))
    label_width = max(len(label) for label, *_ in _COMPARISON_ROWS) + 4
    lines = [" " * label_width + "".join(f"{n:>{width}}" for n in names)]
    for workload, runs in grid.items():
        lines += ["", f"{workload} ({runs[0][1].passengers} passengers)"]
        for label, get, fmt, lower in _COMPARISON_ROWS:
            values = [get(m) for _, m in runs]
            lines.append(
                _render_row(f"  {label}", values, fmt, lower, label_width, width)
            )
    return "\n".join(lines)


def _render_row(
    label: str,
    values: list[float | None],
    fmt: str,
    lower: bool | None,
    label_width: int,
    width: int,
) -> str:
    texts = ["-" if v is None else format(v, fmt) for v in values]
    best = _best(values, texts, lower)
    cells = [f"{t + ('*' if t == best else ' '):>{width}}" for t in texts]
    return f"{label:<{label_width}}" + "".join(cells)


def _best(
    values: list[float | None], texts: list[str], lower: bool | None
) -> str | None:
    """The displayed text of the best value, or None when the row has no
    better direction or every run shows the same value."""
    shown = {t for v, t in zip(values, texts, strict=True) if v is not None}
    if lower is None or len(shown) < 2:
        return None
    pick = min if lower else max
    return texts[values.index(pick(v for v in values if v is not None))]
