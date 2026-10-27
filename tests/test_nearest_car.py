from elevator_sim.config import DispatchStrategy
from elevator_sim.dispatch.nearest_car import NearestCarDispatcher
from elevator_sim.models import Direction, ElevatorRequest, ElevatorView
from elevator_sim.simulation import run_simulation
from tests.helpers import SAMPLE, SAMPLE_BUILDING

UP, DOWN, IDLE = Direction.UP, Direction.DOWN, Direction.IDLE


def car(index, floor, direction=IDLE, dropoffs=()) -> ElevatorView:
    return ElevatorView(
        index=index,
        floor=floor,
        direction=direction,
        load=len(dropoffs),
        capacity=12,
        dropoffs=tuple(dropoffs),
        pickups=(),
    )


def request(source, dest) -> ElevatorRequest:
    return ElevatorRequest.from_tuple((0, "new", source, dest))


def assign(cars, req) -> int:
    return NearestCarDispatcher().assign(req, cars, t=0)


def test_nearest_idle_car_wins():
    assert assign([car(0, 1), car(1, 30)], request(28, 2)) == 1


def test_ties_rotate_through_the_cars():
    cars = [car(0, 5), car(1, 5)]
    dispatcher = NearestCarDispatcher()
    picks = [dispatcher.assign(request(10, 2), cars, t=0) for _ in range(3)]
    assert picks == [0, 1, 0]


def test_car_just_past_the_caller_counts_its_whole_sweep():
    # car0 is one floor above the caller but heading up to 30: 24 + 25 = 49.
    # Idle car1 is 4 floors away.
    cars = [car(0, 6, UP, dropoffs=[30]), car(1, 1)]
    assert NearestCarDispatcher.distance(cars[0], request(5, 9)) == 49
    assert assign(cars, request(5, 9)) == 1


def test_car_coming_the_callers_way_is_taken_at_face_value():
    cars = [car(0, 3, UP, dropoffs=[30]), car(1, 9)]
    assert assign(cars, request(5, 9)) == 0  # 2 floors, vs 4 for the idle car


def test_car_passing_the_other_way_turns_around_first():
    # car0 passes floor 8 going up to 20, then comes back: 16 + 12 = 28.
    cars = [car(0, 4, UP, dropoffs=[20]), car(1, 30)]
    assert NearestCarDispatcher.distance(cars[0], request(8, 2)) == 28
    assert assign(cars, request(8, 2)) == 1  # idle car1: 22


def test_caller_beyond_the_sweep_is_the_new_turnaround():
    # car0 heads up to 8; a caller at 10 going down is reached in 5 floors.
    cars = [car(0, 5, UP, dropoffs=[8]), car(1, 1)]
    assert NearestCarDispatcher.distance(cars[0], request(10, 2)) == 5
    assert NearestCarDispatcher.distance(car(0, 9, DOWN), request(10, 2)) == 1


def test_sample_input():
    # p1 and p2 arrive together with every car idle at the lobby: distance 0
    # for all, so the tie rotates: e0, then e1. At t=10, p3 at floor 20 wants
    # down; e0 and e1 are at 11 heading up (40 + 31 floors), idle e2 and e3
    # are 19 away, and the tie rotates on to e2.
    config = SAMPLE_BUILDING.model_copy(
        update={"dispatch": DispatchStrategy.NEAREST_CAR}
    )
    result = run_simulation(SAMPLE, config)
    assert [p.elevator for p in result.passengers] == [0, 1, 2]
    assert result.completed
