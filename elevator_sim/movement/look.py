from elevator_sim.models import Action, Direction, ElevatorView
from elevator_sim.physics import boarding


class LookPolicy:
    """LOOK: keep sweeping while there is work ahead, then reverse.

    Targets are rider drop-offs plus the car's assigned pickups. Pickups are
    ignored while the car is full (counting the riders who get off here): it
    cannot board anyone, so it serves drop-offs first and comes back.

    At floor f a car stops for a drop-off, or for a pickup going the way the
    car will leave that can actually board (`physics.boarding`: seats may be
    reserved for older pickups further along). The leaving direction is the
    current one if work remains ahead (or a boardable pickup here goes that
    way), otherwise the reverse. That way a pickup going the other way is
    collected at the turnaround, never carried the wrong way first.
    """

    def next_action(self, elevator: ElevatorView) -> Action:
        f = elevator.floor
        # Seats free once the riders for this floor have stepped off.
        room = elevator.capacity - elevator.load + elevator.dropoffs.count(f)
        pickups = elevator.pickups if room > 0 else ()
        pickups_here = [p for p in pickups if p.floor == f]
        other_targets = [x for x in elevator.dropoffs if x != f]
        other_targets += [p.floor for p in pickups if p.floor != f]

        def work_ahead(d: Direction) -> bool:
            return any((x - f) * d > 0 for x in other_targets)

        def pickup_here(d: Direction) -> bool:
            return bool(boarding(pickups, f, d, room))

        if elevator.direction is not Direction.IDLE:
            d = elevator.direction
            reverse = Direction(-d)
            if work_ahead(d) or pickup_here(d):
                departing = d
            elif work_ahead(reverse) or pickup_here(reverse):
                departing = reverse
            else:
                departing = Direction.IDLE
        elif pickups_here:
            # Idle car with people at its floor: serve the longest-waiting first.
            first = min(pickups_here, key=lambda p: (p.request_time, p.arrival_order))
            departing = first.direction
        elif other_targets:
            # Head for the nearest target; on a tie, go up.
            nearest = min(other_targets, key=lambda x: (abs(x - f), x < f))
            departing = Direction.UP if nearest > f else Direction.DOWN
        else:
            departing = Direction.IDLE

        if f in elevator.dropoffs or (departing is not Direction.IDLE and pickup_here(departing)):
            return Action.stop(departing)
        if departing is Direction.IDLE:
            return Action.idle()
        return Action.move(departing)
