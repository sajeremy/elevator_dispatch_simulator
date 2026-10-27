"""Seeded workload generators.

Single-pattern workloads isolate one kind of traffic each, with arrival
times uniform over `duration` ticks:

    morning_rush   lobby -> office floors
    evening_rush   office floors -> lobby
    interfloor     between office floors, never the lobby
    random_trips   any two floors (the tiny benchmark cases)
    idle_gap       two bursts of random trips with a long quiet stretch between

`office_day` models one working day in an office tower: a morning up-peak,
a two-way lunch peak, light inter-floor traffic during the day and an
evening down-peak. Each occupant's trips chain together (every trip starts
where the previous one ended), so the day is consistent per person.

Regenerate the committed file with `python -m elevator_sim.workloads`.
"""

import math
import random
from dataclasses import dataclass
from pathlib import Path

from elevator_sim.elevator_requests import write_requests_csv
from elevator_sim.models import ElevatorRequest

OFFICE_DAY_PATH = Path("data/office_day.csv")
OFFICE_DAY_SEED = 7

LOBBY = 1
# 1 tick = 1 floor of travel. At ~1.5 s per floor, an hour is 2400 ticks.
TICKS_PER_MINUTE = 40


@dataclass(frozen=True, slots=True)
class OfficeDay:
    """The day starts at 07:00 (t=0) and ends at 20:00. Times are minutes after 07:00."""

    num_floors: int = 40
    people_per_floor: int = 40
    attendance: float = 0.9  # share of occupants who come in
    arrive_mean: float = 105  # 08:45
    arrive_sd: float = 30
    lunch_share: float = 0.4  # share of those present who go out for lunch
    lunch_mean: float = 315  # 12:15
    lunch_sd: float = 30
    lunch_minutes: tuple[float, float] = (30, 70)
    meetings_per_person: float = 1.0  # mean inter-floor round trips per person
    meeting_window: tuple[float, float] = (150, 570)  # 09:30 to 16:30
    meeting_minutes: tuple[float, float] = (15, 60)
    leave_mean: float = 615  # 17:15
    leave_sd: float = 35
    day_minutes: float = 780  # until 20:00
    min_gap: float = 5  # minutes between one person's consecutive trips


DEFAULT_OFFICE_DAY = OfficeDay()


def office_day(
    day: OfficeDay = DEFAULT_OFFICE_DAY, seed: int = OFFICE_DAY_SEED
) -> list[ElevatorRequest]:
    rng = random.Random(seed)
    floors = range(LOBBY + 1, day.num_floors + 1)
    requests: list[ElevatorRequest] = []
    for home in floors:
        for seat in range(day.people_per_floor):
            if rng.random() < day.attendance:
                person = f"f{home:02d}s{seat:02d}"
                requests += _person_day(rng, day, person, home, floors)
    return sorted(requests, key=lambda r: r.time)


def _person_day(
    rng: random.Random, day: OfficeDay, person: str, home: int, floors: range
) -> list[ElevatorRequest]:
    """One occupant's trips in time order, each starting where the last one ended."""
    arrive = _clip(
        rng.gauss(day.arrive_mean, day.arrive_sd),
        0,
        day.arrive_mean + 3 * day.arrive_sd,
    )
    leave = _clip(
        rng.gauss(day.leave_mean, day.leave_sd), arrive + 120, day.day_minutes
    )

    # Away-from-desk outings: (start, end, where). Kept only if they fit
    # between arriving and leaving without overlapping an earlier one.
    outings: list[tuple[float, float, str, int]] = []
    if rng.random() < day.lunch_share:
        start = rng.gauss(day.lunch_mean, day.lunch_sd)
        outings.append((start, start + rng.uniform(*day.lunch_minutes), "lunch", LOBBY))
    for n in range(_poisson(rng, day.meetings_per_person)):
        start = rng.uniform(*day.meeting_window)
        other = rng.choice([f for f in floors if f != home])
        outings.append(
            (start, start + rng.uniform(*day.meeting_minutes), f"meet{n}", other)
        )

    trips = [(arrive, "arrive", home)]
    busy_until = arrive
    for start, end, name, where in sorted(outings):
        if start >= busy_until + day.min_gap and end + day.min_gap <= leave:
            trips += [(start, f"{name}-out", where), (end, f"{name}-back", home)]
            busy_until = end
    trips.append((leave, "leave", LOBBY))

    requests = []
    here = LOBBY
    for minute, name, dest in trips:
        tick = round(minute * TICKS_PER_MINUTE)
        requests.append(
            ElevatorRequest.from_tuple((tick, f"{person}-{name}", here, dest))
        )
        here = dest
    return requests


def morning_rush(
    n: int, num_floors: int, duration: int, seed: int
) -> list[ElevatorRequest]:
    return _trips(
        n, duration, seed, lambda rng: (LOBBY, rng.randint(LOBBY + 1, num_floors))
    )


def evening_rush(
    n: int, num_floors: int, duration: int, seed: int
) -> list[ElevatorRequest]:
    return _trips(
        n, duration, seed, lambda rng: (rng.randint(LOBBY + 1, num_floors), LOBBY)
    )


def interfloor(
    n: int, num_floors: int, duration: int, seed: int
) -> list[ElevatorRequest]:
    return _trips(
        n, duration, seed, lambda rng: rng.sample(range(LOBBY + 1, num_floors + 1), 2)
    )


def random_trips(
    n: int, num_floors: int, duration: int, seed: int
) -> list[ElevatorRequest]:
    return _trips(
        n, duration, seed, lambda rng: rng.sample(range(1, num_floors + 1), 2)
    )


def idle_gap(
    n: int, num_floors: int, duration: int, gap: int, seed: int
) -> list[ElevatorRequest]:
    """Half the trips in [0, duration), the rest in [duration + gap, 2 * duration + gap)."""
    first = random_trips(n // 2, num_floors, duration, seed)
    second = random_trips(n - n // 2, num_floors, duration, seed + 1)
    shifted = [
        ElevatorRequest.from_tuple(
            (
                r.time + duration + gap,
                f"late-{r.passenger_id}",
                r.source_floor,
                r.destination_floor,
            )
        )
        for r in second
    ]
    return first + shifted


def _trips(n: int, duration: int, seed: int, pick_floors) -> list[ElevatorRequest]:
    """n trips with times uniform in [0, duration), sorted by time."""
    rng = random.Random(seed)
    trips = []
    for i in range(n):
        time = rng.randrange(duration)
        source, dest = pick_floors(rng)
        trips.append(ElevatorRequest.from_tuple((time, f"p{i}", source, dest)))
    return sorted(trips, key=lambda r: r.time)


def _clip(x: float, low: float, high: float) -> float:
    return min(max(x, low), high)


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth's method; fine for small means."""
    limit, k, p = math.exp(-mean), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


if __name__ == "__main__":
    write_requests_csv(office_day(), OFFICE_DAY_PATH)
    print(f"wrote {OFFICE_DAY_PATH}")
