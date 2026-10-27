"""Direct checks of one car's tick rules that the policies never trigger."""

from elevator_sim.models import Action, Direction, Elevator, ElevatorRequest, Passenger
from elevator_sim.physics import step


def rider(dest: int, floor: int) -> Passenger:
    p = Passenger(
        ElevatorRequest.from_tuple((0, f"to{dest}", floor, dest)),
        elevator=0,
        arrival_order=0,
    )
    p.pickup_time = 0
    return p


def test_moving_a_rider_away_from_their_destination_is_counted():
    car = Elevator(index=0, floor=5, capacity=4, riders=[rider(2, 5), rider(9, 5)])
    outcome = step(car, Action.move(Direction.UP), t=1, stop_duration=1, num_floors=10)
    assert outcome.wrong_way == 1  # the rider for floor 2 moved up
    outcome = step(
        car, Action.move(Direction.DOWN), t=2, stop_duration=1, num_floors=10
    )
    assert outcome.wrong_way == 1  # now the rider for floor 9 moved down
