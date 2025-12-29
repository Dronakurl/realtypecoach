"""Burst detector configuration with Pydantic validation."""

from enum import Enum
from pydantic import BaseModel, Field, validator


class DurationCalculationMethod(str, Enum):
    """Method for calculating burst duration."""

    TOTAL_TIME = 'total_time'
    ACTIVE_TIME = 'active_time'


class BurstDetectorConfig(BaseModel):
    """Configuration for BurstDetector with validation."""

    burst_timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Maximum pause between keystrokes before burst ends (ms)"
    )
    high_score_min_duration_ms: int = Field(
        default=10000,
        gt=0,
        description="Minimum duration for burst to qualify for high score (ms)"
    )
    duration_calculation_method: DurationCalculationMethod = Field(
        default=DurationCalculationMethod.TOTAL_TIME,
        description="How to calculate burst duration"
    )
    active_time_threshold_ms: int = Field(
        default=500,
        gt=0,
        description="For active_time method, max interval to count as active (ms)"
    )
    min_key_count: int = Field(
        default=10,
        ge=1,
        description="Minimum keystrokes required for burst to be recorded"
    )
    min_duration_ms: int = Field(
        default=5000,
        gt=0,
        description="Minimum duration required for burst to be recorded (ms)"
    )

    class Config:
        """Pydantic model configuration."""

        extra = 'ignore'
        use_enum_values = True

    @validator('active_time_threshold_ms')
    def validate_thresholds(cls, v, values):  # noqa: N805
        """Validate interdependent field relationships."""
        if 'burst_timeout_ms' in values and v >= values['burst_timeout_ms']:
            raise ValueError(
                f'active_time_threshold_ms ({v}) must be '
                f'less than burst_timeout_ms ({values["burst_timeout_ms"]})'
            )
        return v


__all__ = ['BurstDetectorConfig', 'DurationCalculationMethod']
