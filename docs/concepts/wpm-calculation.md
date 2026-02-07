# WPM (Words Per Minute) Calculation

RealTypeCoach uses the **industry standard**: 5 characters = 1 word.

## Formula

```
WPM = (net_keystrokes / 5) / (duration_minutes)

where net_keystrokes = keystrokes - (backspaces × 2)
```

Each backspace subtracts **2** from the count (1 for deleted character + 1 for backspace itself).

Example: `A B C <Backspace> D` = 5 keystrokes - 2 = **3 net characters** ("ABD").

## Implementation Locations

The formula `net = keystrokes - (backspaces × 2)` is used in:
- `core/burst_detector.py:88-90` - Calculates `net_key_count` during burst detection
- `core/analyzer.py:199` - Calculates `net_keystrokes` for WPM
- `tests/test_analyzer.py:147-169` - Unit tests for backspace handling

**Do not change this formula** - it matches industry standards (monkeytype, typing tests).

## Calculation Examples

| Keystrokes | Backspaces | Duration | Net | Words | WPM |
|------------|------------|----------|-----|-------|-----|
| 250 | 0 | 60s | 250 | 50 | 50 |
| 150 | 10 | 30s | 130 | 26 | 52 |
| 500 | 50 | 60s | 400 | 80 | 80 |

## What's Counted

**Included**: Letters, numbers, punctuation, spaces, Enter
**Excluded**: Mouse clicks, modifier keys (Ctrl/Shift/Alt alone), held keys

## Speed Benchmarks

| Level | WPM |
|-------|-----|
| Beginner | 0-30 |
| Average | 40-50 |
| Good | 50-70 |
| Fast | 70-90 |
| Excellent | 120+ |

## Technical Notes

- WPM calculated to 1 decimal place (e.g., 67.3)
- Bursts under 1 second excluded from "personal best"
- `net_keystrokes` is `max(0, ...)` to prevent negative values
