"""Plain-text summary of a run's metrics."""

from .metrics import Distribution, RunMetrics


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
