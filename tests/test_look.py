from elevator_sim.models import Action, Direction, ElevatorView, PickupView
from elevator_sim.movement.look import LookPolicy

UP, DOWN, IDLE = Direction.UP, Direction.DOWN, Direction.IDLE


def car(floor, direction=IDLE, dropoffs=(), pickups=(), load=None, capacity=12):
    return ElevatorView(
        index=0,
        floor=floor,
        direction=direction,
        load=len(dropoffs) if load is None else load,
        capacity=capacity,
        dropoffs=tuple(dropoffs),
        pickups=tuple(
            PickupView(
                floor=fl,
                destination_floor=fl + d,  # LOOK only looks at the pickup's direction
                direction=d,
                request_time=i,
                arrival_order=i,
            )
            for i, (fl, d) in enumerate(pickups)
        ),
    )


look = LookPolicy()


def test_idle_with_no_work():
    assert look.next_action(car(5)) == Action.idle()


def test_idle_car_heads_for_nearest_target():
    assert look.next_action(car(5, pickups=[(7, DOWN), (2, UP)])) == Action.move(UP)
    assert look.next_action(car(5, pickups=[(4, UP), (9, DOWN)])) == Action.move(DOWN)


def test_idle_car_breaks_distance_tie_upward():
    assert look.next_action(car(5, pickups=[(3, UP), (7, UP)])) == Action.move(UP)


def test_idle_car_boards_longest_waiting_direction_first():
    view = car(5, pickups=[(5, DOWN), (5, UP)])
    assert look.next_action(view) == Action.stop(DOWN)


def test_keeps_sweeping_while_work_ahead():
    view = car(3, UP, dropoffs=[8], pickups=[(1, UP)])
    assert look.next_action(view) == Action.move(UP)


def test_stops_for_dropoff():
    assert look.next_action(car(8, UP, dropoffs=[8])) == Action.stop(IDLE)


def test_stops_for_dropoff_and_keeps_direction_if_work_ahead():
    assert look.next_action(car(8, UP, dropoffs=[8, 10])) == Action.stop(UP)


def test_stops_for_same_direction_pickup():
    view = car(4, UP, dropoffs=[9], pickups=[(4, UP)])
    assert look.next_action(view) == Action.stop(UP)


def test_passes_opposite_direction_pickup_mid_sweep():
    view = car(4, UP, dropoffs=[9], pickups=[(4, DOWN)])
    assert look.next_action(view) == Action.move(UP)


def test_collects_opposite_direction_pickup_at_turnaround():
    view = car(9, UP, pickups=[(9, DOWN)])
    assert look.next_action(view) == Action.stop(DOWN)


def test_reverses_when_nothing_ahead():
    view = car(9, UP, pickups=[(2, UP)])
    assert look.next_action(view) == Action.move(DOWN)


def test_full_car_ignores_pickups():
    view = car(4, UP, dropoffs=[9, 9], pickups=[(4, UP)], capacity=2)
    assert look.next_action(view) == Action.move(UP)


def test_full_car_does_not_chase_pickups_behind():
    view = car(9, UP, dropoffs=[9, 3], pickups=[(12, DOWN)], capacity=2)
    assert look.next_action(view) == Action.stop(DOWN)
