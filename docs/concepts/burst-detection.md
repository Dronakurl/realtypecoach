# Burst Detection

Burst detection identifies continuous typing periods, separating them from rest periods to measure **sustained typing speed**.

## What is a Burst?

A **burst** is a sequence of keystrokes without a long pause. A pause longer than `burst_timeout_ms` ends the burst and a new one begins on the next keystroke.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `burst_timeout_ms` | 1000ms (1s) | Max pause before burst ends |
| `high_score_min_duration_ms` | 10000ms (10s) | Min duration for high score |
| `duration_calculation_method` | `total_time` | How burst duration is calculated |
| `active_time_threshold_ms` | 500ms | For `active_time` method, max gap to count |
| `min_key_count` | 10 | Min keystrokes to record a burst |
| `min_duration_ms` | 5000ms | Min duration to record a burst |

## Duration Calculation Methods

**`total_time`** (default): Time from first to last keystroke in the burst.

**`active_time`**: Sum of intervals between consecutive keystrokes that are shorter than `active_time_threshold_ms`. Longer gaps within a burst are excluded from duration.

Example with `active_time`: Keys typed at t=0, 200, 500, 1500, 1700ms with threshold=500ms:
- Intervals: 200, 300, **1000** (exceeds threshold), 200
- Active duration: 200 + 300 + 200 = **700ms** (not 1700ms)

## Why Bursts Matter

- **Real typing speed**: Measures active typing, not thinking time
- **Flow state indicator**: Continuous typing vs. fragmented activity
- **Fair comparison**: Like typing tests (active typing only)

## WPM Calculation

```
WPM = (net_keystrokes / 5) / (duration_minutes)

where net_keystrokes = keystrokes - (backspaces × 2)
```

Standard: 5 characters = 1 word.

## Qualification

Not all bursts are equal:

| Criterion | Threshold |
|-----------|-----------|
| **Recorded** | ≥10 keystrokes AND ≥5 seconds |
| **High score** | ≥10 seconds duration |

Short bursts are excluded from "personal best" to prevent inflated scores from typing a single word quickly.
