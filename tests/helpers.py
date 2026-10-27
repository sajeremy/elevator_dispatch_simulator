from elevator_sim.config import DispatchStrategy, SimulationConfig
from elevator_sim.models import ElevatorRequest
from elevator_sim.report import ROWS

# The problem statement's sample building, used with SAMPLE below. Round robin,
# because the hand traces in the tests were worked out for it.
SAMPLE_BUILDING = SimulationConfig(
    num_floors=60, num_elevators=4, capacity=12, dispatch=DispatchStrategy.ROUND_ROBIN
)


def requests(*rows: tuple[int, str, int, int]) -> list[ElevatorRequest]:
    return [ElevatorRequest.from_tuple(r) for r in rows]


SAMPLE = requests(
    (0, "passenger1", 1, 51),
    (0, "passenger2", 1, 37),
    (10, "passenger3", 20, 1),
)


def column(**cells):
    """A values mapping with every ROWS label, None unless given."""
    return dict.fromkeys(r.label for r in ROWS) | cells


def row(text: str, label: str) -> str:
    """The table line for `label`."""
    return next(line for line in text.splitlines() if line.startswith(f"  {label} "))
