# WPM (Words Per Minute) Calculation

## Overview

RealTypeCoach calculates typing speed using the **industry-standard WPM formula**, consistent with typing tests and professional typing measurement tools.

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

**Counted:**
- Letters (a-z)
- Numbers (0-9)
- Punctuation (. , ; : etc.)
- Spaces
- Enter key
- Backspace/delete

**All key presses are counted equally** - we don't penalize mistakes.

### Why Not Penalize Mistakes?

Traditional typing tests subtract errors, but RealTypeCoach **doesn't** because:

1. **Real-world typing**: You use backspace in real typing
2. **Focus on speed**: First step is building raw speed
3. **Natural accuracy**: Speed and accuracy improve together
4. **Not a test**: This is practice, not an exam

### What's NOT Counted

- Mouse clicks
- Modifier keys alone (Ctrl, Shift, Alt by themselves)
- Keys held down (repeat rate not measured)

## Calculation in RealTypeCoach

### For a Burst

```python
def calculate_wpm(key_count: int, duration_ms: int) -> float:
    words = key_count / 5.0
    minutes = duration_ms / 60000.0  # Convert ms to minutes
    return words / minutes if minutes > 0 else 0.0
```

### For Daily Average

```python
total_keystrokes_today = 5420
total_typing_seconds = 600  # 10 minutes

words = 5420 / 5 = 1084 words
minutes = 600 / 60 = 10 minutes
avg_wpm = 1084 / 10 = 108.4 WPM
```

## Comparison to Typing Tests

| Aspect | Typing Tests | RealTypeCoach |
|--------|--------------|---------------|
| Duration | Fixed (1-5 min) | Variable (real usage) |
| Text | Prescribed text | Your natural typing |
| Errors | Penalized | Not penalized |
| Environment | Artificial | Real work/usage |
| Goal | Test score | Ongoing improvement |

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
