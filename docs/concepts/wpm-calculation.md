# WPM (Words Per Minute) Calculation

## Overview

RealTypeCoach calculates typing speed using the **industry-standard WPM formula**, consistent with typing tests and professional typing measurement tools.

## ⚠️ Important: Backspace Calculation

**CRITICAL IMPLEMENTATION NOTE**: The formula for calculating net characters is:

```
net_characters = keystrokes - (backspaces × 2)
```

Each backspace removes **TWO** characters from the count:
1. The backspace keystroke itself
2. The character it deleted

**Example**: Type `A B C <Backspace> D`
- Keystrokes: 5 (A, B, C, Backspace, D)
- Backspaces: 1
- Net: 5 - (1 × 2) = **3 characters** (which equals "ABD")

**This is implemented in 3 locations** (all must use the same formula):
- `core/burst_detector.py:90-92` - Calculates net_key_count during burst detection
- `core/analyzer.py:222` - Calculates WPM from keystrokes
- `tests/test_notification_handler.py:28` - Helper function for test data

**Do NOT change this formula** to `keystrokes - backspaces` - that would incorrectly count corrections!

## The Standard Formula

```
WPM = (keystrokes / 5) / (minutes_of_typing)
```

### Why Divide by 5?

The standard assumption: **1 word = 5 characters**

This is based on:
- Average word length in English: ~4.5 characters
- Plus 1 space between words
- Rounds to 5 characters per word

**Industry Standard**: Used by:
- Typing.com
- 10FastFingers
- Professional typing assessment tools
- Administrative job requirements

## Calculation Examples

### Example 1: Moderate Typing
```
Keystrokes: 250
Duration: 60 seconds (1 minute)

Words = 250 / 5 = 50 words
WPM = 50 / 1 = 50 WPM
```

### Example 2: Fast Typing
```
Keystrokes: 500
Duration: 60 seconds (1 minute)

Words = 500 / 5 = 100 words
WPM = 100 / 1 = 100 WPM
```

### Example 3: Short Duration
```
Keystrokes: 100
Duration: 30 seconds

Words = 100 / 5 = 20 words
Minutes = 30 / 60 = 0.5 minutes
WPM = 20 / 0.5 = 40 WPM
```

## What RealTypeCoach Tracks

### 1. Current WPM

Your **overall average** WPM for today, calculated from:
```
Total keystrokes today / Total typing time today
```

### 2. Burst WPM

Your **current/recent burst** WPM, showing:
- Speed during your most recent active typing period
- Updates in real-time as you type
- Reflects current performance, not historical

### 3. Personal Best Today

**Highest burst WPM** today that met the minimum duration requirement (10+ seconds)

This represents your **peak performance** for the day.

## Typing Speed Categories

| Speed Level | WPM Range | Description |
|-------------|-----------|-------------|
| Beginner | 0-30 WPM | Hunt and peck, new typist |
| Slow | 30-40 WPM | Familiar with keyboard |
| Average | 40-50 WPM | Typical office worker |
| Good | 50-70 WPM | Touch typist |
| Fast | 70-90 WPM | Experienced touch typist |
| Very Fast | 90-120 WPM | Professional typist |
| Excellent | 120+ WPM | Exceptional, top 1% |

## Accuracy Considerations

### What Counts as a "Keystroke"?

**Productive keystrokes counted:**
- Letters (a-z)
- Numbers (0-9)
- Punctuation (. , ; : etc.)
- Spaces
- Enter key

**Corrected keystrokes (backspaces):**
Each backspace removes TWO characters from the count:
- **-1** for the backspace keystroke itself
- **-1** for the character it deleted

Example: If you type "ABC" then press backspace and type "D":
- Total keystrokes: 5 (A, B, C, Backspace, D)
- Backspaces: 1
- **Net keystrokes: 5 - (1 × 2) = 3** (which equals "ABD")
- This matches industry standards like monkeytype

### Why Count This Way?

This method reflects the **actual text produced**, not the effort:

1. **Fair comparison**: Matches how typing tests like monkeytype calculate WPM
2. **Realistic measurement**: Counts what actually appears on screen
3. **Encourages accuracy**: Corrections reduce the final count naturally
4. **Standard compliance**: Aligns with professional typing measurement tools

### What's NOT Counted

- Mouse clicks
- Modifier keys alone (Ctrl, Shift, Alt by themselves)
- Keys held down (repeat rate not measured)

## Calculation in RealTypeCoach

### For a Burst

```python
def calculate_wpm(key_count: int, backspace_count: int, duration_ms: int) -> float:
    # Each backspace removes 1 character + itself = 2 net reduction
    net_keystrokes = key_count - (backspace_count * 2)
    words = net_keystrokes / 5.0
    minutes = duration_ms / 60000.0  # Convert ms to minutes
    return words / minutes if minutes > 0 else 0.0
```

Example: 150 keystrokes, 10 backspaces, 30 seconds
- Net: 150 - (10 × 2) = 130 keystrokes
- Words: 130 / 5 = 26 words
- Minutes: 30 / 60 = 0.5 minutes
- **WPM: 26 / 0.5 = 52 WPM**

### For Daily Average

```python
total_keystrokes_today = 5420
total_typing_seconds = 600  # 10 minutes

words = 5420 / 5 = 1084 words
minutes = 600 / 60 = 10 minutes
avg_wpm = 1084 / 10 = 108.4 WPM
```

## Comparison to Typing Tests

| Aspect | Typing Tests (e.g., monkeytype) | RealTypeCoach |
|--------|--------------|---------------|
| Duration | Fixed (1-5 min) | Variable (real usage) |
| Text | Prescribed text | Your natural typing |
| Errors | Only correct characters count | Only correct characters count ✓ |
| Environment | Artificial | Real work/usage |
| Goal | Test score | Ongoing improvement |

**Note**: RealTypeCoach's WPM calculation now matches industry standards like monkeytype by counting only the final, corrected characters.

## Improving Your WPM

### Target Goals

- **Week 1**: Measure baseline (don't change anything)
- **Month 1**: +10-20 WPM improvement
- **3 Months**: +20-30 WPM improvement
- **6 Months**: Reach target WPM (usually 60-80 WPM)

### Practice Strategies

1. **Focus on slowest keys** (see Key Speed Metrics)
2. **Maintain bursts** - try to type continuously
3. **Home row practice** - keep fingers on home row
4. **Don't look at hands** - build muscle memory

### Realistic Expectations

- **Beginner (30 WPM)** → 40-50 WPM: 1-3 months
- **Average (50 WPM)** → 70+ WPM: 3-6 months
- **Good (70 WPM)** → 100+ WPM: 6-12 months

Consistency matters more than intensity!

## Technical Notes

### Precision

- WPM is calculated to **1 decimal place** (e.g., 67.3 WPM)
- Fractions matter for tracking small improvements
- Bursts under 1 second are rounded to avoid inflated WPM

### Edge Cases

- **Duration = 0**: Returns 0 WPM (avoids division by zero)
- **Very short bursts**: Can have very high WPM (e.g., 3 chars in 100ms = 360 WPM!)
  - These are excluded from "personal best" (minimum duration filter)
