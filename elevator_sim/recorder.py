import csv
from collections.abc import Sequence
from pathlib import Path


class PositionRecorder:
    """Collects one row of elevator floors per tick. Observes only."""

    def __init__(self, num_elevators: int) -> None:
        self.header = ("time", *(f"e{i}" for i in range(num_elevators)))
        self.rows: list[tuple[int, ...]] = []

    def record(self, t: int, floors: Sequence[int]) -> None:
        self.rows.append((t, *floors))

    def write_csv(self, path: str | Path) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.header)
            writer.writerows(self.rows)
