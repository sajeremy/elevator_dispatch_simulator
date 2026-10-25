from elevator_sim.models import Request


def requests(*rows: tuple[int, str, int, int]) -> list[Request]:
    return [Request.from_tuple(r) for r in rows]


SAMPLE = requests(
    (0, "passenger1", 1, 51),
    (0, "passenger2", 1, 37),
    (10, "passenger3", 20, 1),
)
