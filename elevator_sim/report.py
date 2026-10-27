"""Plain-text summary of a run's metrics, and a side-by-side comparison of runs."""

from collections.abc import Sequence

from elevator_sim.metrics import Distribution, RunMetrics


def _row(name: str, d: Distribution | None, fmt: str = ".0f") -> str:
    if d is None:
        return f"  {name:<8} (no delivered passengers)"
    return (
        f"  {name:<8} min {d.min:>7{fmt}}  max {d.max:>7{fmt}}  "
        f"mean {d.mean:>7.2f}  p95 {d.p95:>7{fmt}}"
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
    return notes


def format_report(m: RunMetrics) -> str:
    lines = [
        f"Passengers: {m.delivered}/{m.passengers} delivered in {m.ticks} ticks",
        "",
        "Times (ticks)",
        _row("wait", m.wait),
        _row("travel", m.travel),
        _row("total", m.total),
        _row("stretch", m.stretch, ".2f"),
        "",
        "Elevators",
    ]
    for e in m.elevators:
        lines.append(
            f"  e{e.index}  served {e.passengers_served:>4}  busy {e.utilization:>4.0%}  "
            f"(moving {e.moving_ticks}, stopped {e.stopped_ticks}, idle {e.idle_ticks})"
        )
    notes = observations(m)
    if notes:
        lines += ["", "Observations"] + [f"  - {n}" for n in notes]
    return "\n".join(lines)


def _distribution_rows(name: str, attr: str, fmt: str) -> list[tuple]:
    return [
        (f"{name} {stat}", lambda m, s=stat: _stat(getattr(m, attr), s), fmt, True)
        for stat in ("min", "mean", "p95", "max")
    ]


def _stat(d: Distribution | None, stat: str) -> float | None:
    return None if d is None else getattr(d, stat)


def _overhead(m: RunMetrics) -> float | None:
    return m.total_time_sum / m.ideal_total_sum - 1 if m.ideal_total_sum else None


def _wait_share(m: RunMetrics) -> float | None:
    if not (m.wait and m.total_time_sum):
        return None
    return m.wait.mean * m.wait.count / m.total_time_sum


def _busy(m: RunMetrics, pick) -> float | None:
    return pick(e.utilization for e in m.elevators) if m.elevators else None


# (label, value from a run's metrics, number format, whether lower is better).
# Rows with no better direction (None) are shown but never starred.
_COMPARISON_ROWS = [
    ("delivered", lambda m: m.delivered, "d", False),
    ("run ticks", lambda m: m.ticks, "d", True),
    *_distribution_rows("wait", "wait", ".1f"),
    *_distribution_rows("travel", "travel", ".1f"),
    *_distribution_rows("total", "total", ".1f"),
    *_distribution_rows("stretch", "stretch", ".2f"),
    ("over private-car bound", _overhead, ".0%", True),
    ("waiting share of time", _wait_share, ".0%", True),
    ("busiest car busy", lambda m: _busy(m, max), ".0%", None),
    ("least busy car busy", lambda m: _busy(m, min), ".0%", None),
    (
        "busy spread (max - min)",
        lambda m: _busy(m, max) - _busy(m, min) if m.elevators else None,
        ".0%",
        True,
    ),
]

# Headline rows for the summary against the first column.
_HEADLINES = ("wait mean", "wait p95", "wait max", "total mean", "stretch mean")


def format_comparison(
    runs: Sequence[tuple[str, RunMetrics]], seconds: Sequence[float] = ()
) -> str:
    """Metrics side by side, one column per run. `*` marks the best value in
    a row when the runs differ; ties all get it. The summary compares each
    run with the first one."""
    names = [name for name, _ in runs]
    width = max(12, *(len(n) + 2 for n in names))
    label_width = max(len(label) for label, *_ in _COMPARISON_ROWS) + 2
    rows = [
        (label, [get(m) for _, m in runs], fmt, lower)
        for label, get, fmt, lower in _COMPARISON_ROWS
    ]
    if seconds:
        rows.append(("run time (s)", list(seconds), ".2f", True))

    lines = [
        f"Dispatch comparison ({runs[0][1].passengers} passengers)",
        "",
        " " * label_width + "".join(f"{n:>{width}}" for n in names),
    ]
    for label, values, fmt, lower in rows:
        texts = ["-" if v is None else format(v, fmt) for v in values]
        best = _best(values, texts, lower)
        cells = [f"{t + ('*' if t == best else ' '):>{width}}" for t in texts]
        lines.append(f"{label:<{label_width}}" + "".join(cells))

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
