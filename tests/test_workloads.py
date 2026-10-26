from collections import defaultdict
from itertools import pairwise

from elevator_sim.elevator_requests import load_requests_csv, write_requests_csv
from elevator_sim.workloads import LOBBY, OFFICE_DAY_PATH, OfficeDay, office_day


def test_committed_office_day_matches_the_generator():
    assert load_requests_csv(OFFICE_DAY_PATH) == office_day()


def test_same_seed_same_day_other_seed_differs():
    assert office_day(seed=1) == office_day(seed=1)
    assert office_day(seed=1) != office_day(seed=2)


def test_each_persons_trips_chain_from_lobby_back_to_lobby():
    day = OfficeDay(num_floors=12, people_per_floor=10)
    trips = defaultdict(list)
    for r in office_day(day, seed=3):
        trips[r.passenger_id.split("-")[0]].append(r)

    assert trips
    for person, rs in trips.items():
        assert [r.time for r in rs] == sorted(r.time for r in rs), person
        assert rs[0].source_floor == LOBBY and rs[-1].destination_floor == LOBBY
        for before, after in pairwise(rs):
            assert before.destination_floor == after.source_floor, person
            assert 1 <= after.source_floor <= day.num_floors


def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "day.csv"
    requests = office_day(OfficeDay(num_floors=5, people_per_floor=3))
    write_requests_csv(requests, path)
    assert load_requests_csv(path) == requests
