# Problem Statement

A discrete-time simulation of a multi-elevator building using destination dispatch, built to compare scheduling algorithms.

## Goals

1. **Serve every request.** No passenger waits indefinitely to be picked up or dropped off.
2. **Minimize total time per passenger:** `total_time = wait_time + travel_time`.
3. **Respect elevator constraints,** including capacity and direction of travel.

## Destination dispatch

- A passenger enters both origin and destination floor when making a request.
- The controller assigns the passenger to one elevator immediately.
- The assignment and destination are fixed after that.

## Time model

- One time unit is one floor of travel, up or down.
- No real-clock synchronization.
- The simulation advances one time unit at a time, even across gaps between requests.

## Configuration

- Number of elevators (e.g. 1–10)
- Number of floors
- Maximum passengers per elevator
- Scheduling algorithm

## Input

A list of requests:

```
time,id,source,dest
0,passenger1,1,51
0,passenger2,1,37
10,passenger3,20,1
```

| Field | Meaning |
|---|---|
| `time` | Time step the request is made |
| `id` | Unique passenger ID |
| `source` | Origin floor |
| `dest` | Destination floor |

The scheduler never sees a request before its `time`.

## Output

1. **Elevator positions log:** one row per time step, starting at 0, with every elevator's floor.
2. **Passenger statistics:** min, max and average wait time and total time, plus other observations about the distributions and system behavior.

## Stretch goals

- Multiple algorithms to compare (round robin, nearest car, zone-based)
- Express elevators that skip floors
- Fairness (bounding the worst wait) vs. efficiency (serving the majority flow)
