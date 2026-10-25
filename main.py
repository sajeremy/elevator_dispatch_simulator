from pydantic import BaseModel, ConfigDict, Field


class DestinationCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: int = Field(ge=0, description="Time step at which the request is made.")
    passenger_id: str = Field(description="Unique identifier of the passenger.")
    source_floor: int = Field(ge=1, description="Floor the passenger is waiting on.")
    destination_floor: int = Field(
        ge=1, description="Floor the passenger wants to go to."
    )

    @classmethod
    def from_tuple(cls, raw: tuple[int, str, int, int]) -> DestinationCall:
        """Build a DestinationCall from a (time, passenger_id, source_floor, destination_floor) tuple."""
        time, passenger_id, source_floor, destination_floor = raw
        return cls(
            time=time,
            passenger_id=passenger_id,
            source_floor=source_floor,
            destination_floor=destination_floor,
        )


calls: list[DestinationCall] = [
    DestinationCall.from_tuple(raw)
    for raw in [
        # Lobby up-peak: several passengers arrive at once
        (0, "p1", 1, 5),
        (0, "p2", 1, 8),
        (0, "p3", 1, 10),
        (1, "p4", 1, 5),
        # Down traffic from upper floors
        (2, "p5", 10, 1),
        (3, "p6", 7, 1),
        # Interfloor trips in both directions
        (4, "p7", 3, 6),
        (4, "p8", 6, 3),
        # Same source floor, opposite directions
        (6, "p9", 5, 9),
        (6, "p10", 5, 2),
        # Later quiet period
        (12, "p11", 2, 1),
        (15, "p12", 9, 4),
    ]
]


def main():
    print("Hello from elevator-dispatch-simulator!")


if __name__ == "__main__":
    main()
