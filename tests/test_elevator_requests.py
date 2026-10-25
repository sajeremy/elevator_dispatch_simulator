import pytest
from pydantic import ValidationError

from elevator_sim.elevator_requests import RequestSource, load_requests_csv
from elevator_sim.models import ElevatorRequest


def req(time: int, pid: str, source: int, dest: int) -> ElevatorRequest:
    return ElevatorRequest.from_tuple((time, pid, source, dest))


def test_never_releases_a_request_before_its_time():
    source = RequestSource([req(0, "a", 1, 5), req(3, "b", 2, 1), req(3, "c", 4, 9)], 10)
    assert [r.passenger_id for r in source.arrivals_at(0)] == ["a"]
    assert source.arrivals_at(1) == []
    assert source.arrivals_at(2) == []
    assert [r.passenger_id for r in source.arrivals_at(3)] == ["b", "c"]
    assert source.exhausted


def test_each_request_is_released_once():
    source = RequestSource([req(0, "a", 1, 5)], 10)
    assert len(source.arrivals_at(0)) == 1
    assert source.arrivals_at(0) == []


def test_unsorted_input_is_sorted_and_ties_keep_input_order():
    source = RequestSource(
        [req(5, "late", 1, 2), req(0, "x", 1, 2), req(0, "y", 3, 2), req(0, "z", 2, 3)], 10
    )
    assert [r.passenger_id for r in source.arrivals_at(0)] == ["x", "y", "z"]
    assert source.arrivals_at(4) == []
    assert [r.passenger_id for r in source.arrivals_at(5)] == ["late"]


def test_skipped_ticks_still_release_everything_due():
    source = RequestSource([req(1, "a", 1, 2), req(2, "b", 1, 2)], 10)
    assert [r.passenger_id for r in source.arrivals_at(2)] == ["a", "b"]


def test_time_cannot_go_backwards():
    source = RequestSource([req(0, "a", 1, 2)], 10)
    source.arrivals_at(3)
    with pytest.raises(ValueError, match="backwards"):
        source.arrivals_at(2)


def test_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        RequestSource([req(0, "a", 1, 2), req(1, "a", 2, 3)], 10)


def test_rejects_floors_outside_building():
    with pytest.raises(ValueError, match="outside"):
        RequestSource([req(0, "a", 1, 11)], 10)


def test_rejects_zero_length_trip():
    with pytest.raises(ValidationError, match="source and destination"):
        req(0, "a", 3, 3)


def test_rejects_negative_time():
    with pytest.raises(ValidationError):
        req(-1, "a", 1, 2)


def test_load_csv(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("time,id,source,dest\n0,passenger1,1,51\n10,passenger3,20,1\n")
    requests = load_requests_csv(path)
    assert [(r.time, r.passenger_id, r.source_floor, r.destination_floor) for r in requests] == [
        (0, "passenger1", 1, 51),
        (10, "passenger3", 20, 1),
    ]


def test_load_csv_names_bad_line(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("time,id,source,dest\n0,a,1,5\n0,b,4,4\n")
    with pytest.raises(ValueError, match="line 3"):
        load_requests_csv(path)
