"""Pydantic models for RealTypeCoach data structures."""

from pydantic import BaseModel, Field


class DailySummary(BaseModel):
    """Daily typing summary notification data."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message body")
    slowest_key: str = Field(..., description="Slowest key name")
    avg_wpm: str = Field(..., description="Average WPM as string")
    keystrokes: str = Field(..., description="Total keystrokes count as string")

    class Config:
        extra = "ignore"


class DailySummaryDB(BaseModel):
    """Daily typing summary from database."""

    total_keystrokes: int = Field(..., description="Total keystrokes typed")
    total_bursts: int = Field(..., description="Total typing bursts")
    avg_wpm: float = Field(..., description="Average words per minute")
    slowest_keycode: int = Field(..., description="Slowest key keycode")
    slowest_key_name: str = Field(..., description="Slowest key name")
    total_typing_sec: int = Field(..., description="Total typing time in seconds")
    summary_sent: bool = Field(
        default=False, description="Whether daily summary was sent"
    )

    class Config:
        extra = "ignore"


class KeyPerformance(BaseModel):
    """Key performance metric (for slowest/fastest keys lists)."""

    keycode: int = Field(..., description="Linux evdev keycode")
    key_name: str = Field(..., description="Human-readable key name")
    avg_press_time: float = Field(..., description="Average press time in milliseconds")

    class Config:
        extra = "ignore"


class WordStatisticsLite(BaseModel):
    """Lightweight word statistics for lists."""

    word: str = Field(..., description="The word")
    avg_speed_ms_per_letter: float = Field(
        ..., description="Average speed per letter in ms"
    )
    total_duration_ms: int = Field(..., description="Total duration in milliseconds")
    total_letters: int = Field(..., description="Total number of letters")

    class Config:
        extra = "ignore"


class WordStatisticsFull(BaseModel):
    """Complete word statistics from database."""

    word: str = Field(..., description="The word")
    layout: str = Field(..., description="Keyboard layout")
    avg_speed_ms_per_letter: float = Field(
        ..., description="Average speed per letter in ms"
    )
    total_letters: int = Field(..., description="Total number of letters")
    total_duration_ms: int = Field(..., description="Total duration in milliseconds")
    observation_count: int = Field(..., description="Number of observations")
    last_seen: int = Field(..., description="Last seen timestamp")
    backspace_count: int = Field(default=0, description="Number of backspaces used")
    editing_time_ms: int = Field(default=0, description="Time spent editing in ms")

    class Config:
        extra = "ignore"


class BurstTimeSeries(BaseModel):
    """Burst data point for time series graph."""

    timestamp_ms: int = Field(..., description="Burst start timestamp in milliseconds")
    avg_wpm: float = Field(..., description="Average WPM during burst")

    class Config:
        extra = "ignore"


class TypingTimeDataPoint(BaseModel):
    """Typing time and WPM aggregated data point for time series."""

    period_start: int = Field(..., description="Period start timestamp (ms)")
    period_end: int = Field(..., description="Period end timestamp (ms)")
    period_label: str = Field(
        ..., description="Human-readable period label (e.g., '2025-01-15')"
    )
    total_typing_ms: int = Field(..., description="Total typing time in milliseconds")
    total_bursts: int = Field(..., description="Number of bursts in period")
    avg_wpm: float = Field(..., description="Average WPM for the period")

    class Config:
        extra = "ignore"


class KeystrokeInfo(BaseModel):
    """Single keystroke in word tracking."""

    key: str = Field(..., description="Key character")
    time: int = Field(..., description="Timestamp in milliseconds")
    type: str = Field(..., description="Type: 'letter' or 'backspace'")
    keycode: int | None = Field(default=None, description="Linux evdev keycode")

    class Config:
        extra = "ignore"


class WordInfo(BaseModel):
    """Completed word information from WordDetector."""

    word: str = Field(..., description="The typed word")
    layout: str = Field(..., description="Keyboard layout")
    total_duration_ms: int = Field(..., description="Total duration in milliseconds")
    editing_time_ms: int = Field(..., description="Time spent editing with backspace")
    backspace_count: int = Field(..., description="Number of backspaces used")
    num_letters: int = Field(..., description="Number of letters in word")
    keystrokes: list[KeystrokeInfo] = Field(
        default_factory=list, description="List of keystrokes in this word"
    )

    class Config:
        extra = "ignore"


class BurstInfo(BaseModel):
    """Current burst information from BurstDetector."""

    key_count: int = Field(..., description="Number of keystrokes")
    duration_ms: int = Field(..., description="Duration in milliseconds")
    qualifies: bool = Field(..., description="Whether qualifies for high score")

    class Config:
        extra = "ignore"


class DailyStats(BaseModel):
    """Daily statistics tracking in Analyzer."""

    total_keystrokes: int = Field(default=0, description="Total keystrokes")
    total_bursts: int = Field(default=0, description="Total bursts")
    total_typing_ms: int = Field(default=0, description="Total typing time in ms")
    slowest_keycode: int | None = Field(default=None, description="Slowest key keycode")
    slowest_key_name: str | None = Field(default=None, description="Slowest key name")
    slowest_ms: float = Field(default=0.0, description="Slowest key time in ms")
    keypress_times: dict[int, float] = Field(
        default_factory=dict, description="Intervals per key"
    )
    last_press_time: int = Field(default=0, description="Last press time (global)")

    class Config:
        extra = "ignore"


class WorstLetterChange(BaseModel):
    """Worst letter change notification data."""

    previous_key: str = Field(..., description="Previous worst letter key name")
    new_key: str = Field(..., description="New worst letter key name")
    previous_time_ms: float = Field(..., description="Previous worst letter time (ms)")
    new_time_ms: float = Field(..., description="New worst letter time (ms)")
    timestamp: int = Field(..., description="Change timestamp in milliseconds")
    improvement: bool = Field(
        ..., description="True if the new worst letter is faster (improvement)"
    )

    class Config:
        extra = "ignore"
