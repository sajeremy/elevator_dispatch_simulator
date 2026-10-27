from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DispatchStrategy(StrEnum):
    # Simplest to most informed, which is also the comparison table's column order.
    ROUND_ROBIN = "round_robin"
    NEAREST_CAR = "nearest_car"
    ETD = "etd"


class SimulationConfig(BaseModel):
    """Floors are 1-indexed: floor 1 is the lobby."""

    model_config = ConfigDict(frozen=True)

    num_floors: int = Field(
        default=60,
        ge=2,  # a valid request needs two distinct floors
        description="Number of floors; floors are numbered 1..num_floors.",
    )
    num_elevators: int = Field(
        default=4,
        ge=1,
        description="Number of elevators in the building.",
    )
    capacity: int = Field(
        default=12,
        ge=1,
        description="Maximum number of passengers per elevator.",
    )
    start_floor: int = Field(
        default=1,
        ge=1,
        description="Floor where every elevator starts.",
    )
    stop_duration: int = Field(
        default=1,
        ge=1,
        description="Ticks an elevator spends at a stop (doors, boarding, alighting).",
    )
    dispatch: DispatchStrategy = Field(
        default=DispatchStrategy.ROUND_ROBIN,
        description="Strategy used to assign each request to an elevator.",
    )
    max_ticks: int = Field(
        default=100_000,
        ge=1,
        description="Safety cap on simulation length.",
    )

    @model_validator(mode="after")
    def _start_floor_in_building(self) -> Self:
        if self.start_floor > self.num_floors:
            raise ValueError(
                f"start_floor ({self.start_floor}) must be <= num_floors ({self.num_floors})"
            )
        return self
