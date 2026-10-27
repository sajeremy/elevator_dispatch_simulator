"""Two charts, drawn from the results the command that writes them just produced.

    wait_by_hour       mean wait per hour of request per dispatcher, with trip volume
    benchmark_ratios   total time relative to the offline optimum, per tiny scenario

The clock is the office day's: 2,400 ticks per hour from 07:00 (`workloads`).
Other inputs are bucketed on that clock too. Dispatchers keep one colour each
in a fixed order (round robin, nearest car, ETD). Lines are 2px, markers
carry a surface-coloured ring, grid and axes stay recessive.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from elevator_sim.config import DispatchStrategy
from elevator_sim.metrics import summarize
from elevator_sim.models import Passenger
from elevator_sim.workloads import TICKS_PER_MINUTE

TICKS_PER_HOUR = 60 * TICKS_PER_MINUTE
START_HOUR = 7

# Chart chrome (light surface) and the categorical palette, in fixed slot order.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
_STRATEGY_SLOT = {s.value: i for i, s in enumerate(DispatchStrategy)}

LINE = 2.0
MARKER = 6.0  # points; about 8px at the saved resolution


def color_for(label: str, index: int) -> str:
    """A dispatcher always gets its own slot; anything else takes `index`.
    Past eight series the colour folds to the muted ink rather than cycling."""
    slot = _STRATEGY_SLOT.get(label.replace(" ", "_"), index)
    return SERIES[slot] if slot < len(SERIES) else MUTED


@dataclass(frozen=True, slots=True)
class HourBucket:
    hour: int
    trips: int
    mean_wait: float
    p95_wait: float


def hourly(
    passengers: Iterable[Passenger],
    ticks_per_hour: int = TICKS_PER_HOUR,
    start_hour: int = START_HOUR,
) -> list[HourBucket]:
    """Wait statistics per hour of request, for passengers who were picked up."""
    waits: dict[int, list[int]] = {}
    for p in passengers:
        if p.pickup_time is not None:
            hour = start_hour + p.request.time // ticks_per_hour
            waits.setdefault(hour, []).append(p.wait)
    return [
        HourBucket(h, d.count, d.mean, d.p95)
        for h in sorted(waits)
        if (d := summarize(waits[h])) is not None
    ]


def _chrome(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK_SECONDARY, length=0)
    ax.grid(True, color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def _save(fig, out: Path) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def wait_by_hour(
    series: Sequence[tuple[str, Sequence[Passenger]]],
    out: Path,
    ticks_per_hour: int = TICKS_PER_HOUR,
    start_hour: int = START_HOUR,
) -> None:
    """Mean wait per hour of request (top) over the trips requested that hour
    (bottom), one line per (label, passengers) series; each line's peak hour
    is labelled (hours with under 2% of the trips are too quiet to count)."""
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9.6, 5.6), sharex=True, height_ratios=(3, 1)
    )
    volume: dict[int, int] = {}
    for i, (label, passengers) in enumerate(series):
        buckets = hourly(passengers, ticks_per_hour, start_hour)
        if not buckets:
            continue
        colour = color_for(label, i)
        top.plot(
            [b.hour for b in buckets],
            [b.mean_wait for b in buckets],
            color=colour,
            linewidth=LINE,
            marker="o",
            ms=MARKER,
            mec=SURFACE,
            mew=1.5,
            label=label,
        )
        floor = 0.02 * sum(b.trips for b in buckets)
        peak = max((b for b in buckets if b.trips >= floor), key=lambda b: b.mean_wait)
        top.annotate(
            f"{peak.mean_wait:.0f}",
            (peak.hour, peak.mean_wait),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            color=INK_SECONDARY,
        )
        for b in buckets:
            volume[b.hour] = max(volume.get(b.hour, 0), b.trips)
    bottom.bar(list(volume), list(volume.values()), width=0.8, color=AXIS)
    for ax in (top, bottom):
        _chrome(ax)
    top.set_title("Mean wait by hour of request", loc="left", fontsize=11)
    top.set_ylabel("Ticks")
    top.set_ylim(bottom=0)
    if volume:
        top.legend(loc="upper right", frameon=False, labelcolor=INK_SECONDARY)
    bottom.set_title("Trips requested", loc="left", fontsize=11)
    bottom.set_xlabel("Hour of day")
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda h, _: f"{int(h):02d}:00"))
    bottom.set_xticks(sorted(volume))
    _save(fig, out)


def benchmark_ratios(
    scenarios: Sequence[tuple[str, Mapping[str, tuple[float, float]]]], out: Path
) -> None:
    """One panel per (scenario, {dispatcher: (mean, worst)}): a dot at the
    mean ratio of total time to the optimum, a line up to the worst case,
    and a dashed line at 1.0, the optimum itself."""
    fig, axes = plt.subplots(
        1,
        len(scenarios),
        figsize=(3.4 * len(scenarios), 4.2),
        sharey=True,
        squeeze=False,
    )
    for ax, (name, by_dispatcher) in zip(axes[0], scenarios, strict=True):
        for x, (label, (mean, worst)) in enumerate(by_dispatcher.items()):
            colour = color_for(label, x)
            ax.vlines(x, mean, worst, color=colour, linewidth=LINE)
            ax.plot(x, mean, "o", ms=MARKER, mfc=colour, mec=SURFACE, mew=1.5)
        ax.axhline(1.0, color=INK_SECONDARY, linestyle="--", linewidth=1)
        _chrome(ax)
        ax.set_title(name, loc="left", fontsize=11)
        ax.set_xticks(
            range(len(by_dispatcher)), [d.replace("_", "\n") for d in by_dispatcher]
        )
        ax.set_xlim(-0.6, len(by_dispatcher) - 0.4)
    axes[0][0].set_ylabel("total time / optimum")
    fig.suptitle(
        "Total time relative to the offline optimum (dot: mean, line: up to the worst case)",
        x=0.01,
        ha="left",
        color=INK,
        fontsize=12,
    )
    _save(fig, out)
