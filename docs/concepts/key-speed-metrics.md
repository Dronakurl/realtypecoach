# Key Speed Metrics

## Overview

RealTypeCoach tracks the individual speed of each key on your keyboard to help you identify which keys slow down your typing.

## How Key Speed is Calculated

### Measurement: Time Between Presses

For each key on your keyboard, RealTypeCoach measures the **time interval between consecutive presses** of the same key.

**Example:**
```
Press 'A' at time: 1000ms
Press 'A' again at time: 1250ms
Time interval = 1250ms - 1000ms = 250ms
```

### Average Press Time

After collecting multiple intervals for a key, we calculate the **average press time**:

```
Average = (Interval₁ + Interval₂ + ... + Intervalₙ) / n
```

**Example:**
```
First 'A' to 'A': 250ms
Second 'A' to 'A': 230ms
Third 'A' to 'A': 270ms
Average = (250 + 230 + 270) / 3 = 250ms
```

### Minimum Requirements

A key must be pressed **at least 2 times** before we calculate its average speed. This prevents:
- First-time press data from skewing results
- Random single presses from creating meaningless statistics

## What the Numbers Mean

### Slowest Keys

High average press time = **Slower key**

**Example causes:**
- **Physical key issues**: Sticky key, weak spring
- **Finger weakness**: Pinky/ring fingers are naturally weaker
- **Unfamiliar keys**: Rarely used symbols (`,`, `[`, `\`)
- **Stretching**: Keys far from home row (like `Backspace`, `Enter`)

**Typical slow key times:**
- **200-300ms**: Normal for rarely used keys
- **300-500ms**: Indicates possible difficulty
- **500ms+**: Significantly slows typing, worth practicing

### Fastest Keys

Low average press time = **Faster key**

**Typical fast key times:**
- **80-120ms**: Very fast, touch typist level
- **120-150ms**: Good speed
- **150-200ms**: Average, comfortable typing

## How to Use This Data

### Identify Problem Keys

Look for keys that:
1. Are **consistently slow** (high in your slowest list)
2. You use **frequently** (vowels, common consonants)
3. Have **significantly higher** times than your average

### Practice Strategies

1. **Slowest keys first**: Focus on your #1 slowest key
2. **Frequency-weighted**: Prioritize slow keys you use often
3. **Home row focus**: Ensure home row keys are fastest
4. **Stretch practice**: Practice reaching for far keys

### Expected Improvement

With conscious practice, most people see:
- **Week 1**: Awareness of slow keys
- **Week 2-3**: 20-30% improvement on practiced keys
- **Month 1**: 30-50% overall improvement

## Technical Details

### Data Storage

Key speed data is stored in the `statistics` table:

```sql
CREATE TABLE statistics (
    keycode INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_press_time REAL,        -- Average time between presses (ms)
    total_presses INTEGER,       -- Total number of times pressed
    slowest_ms REAL,            -- Slowest interval recorded
    fastest_ms REAL,            -- Fastest interval recorded
    PRIMARY KEY (keycode, layout)
)
```

### Keyboard Layouts

Speed is tracked **separately per keyboard layout** (US, DE, DVORAK, etc.) since the same keycode may represent different characters on different layouts.

### Per-Session vs All-Time

- **During session**: Tracks cumulative averages
- **After restart**: Loads from database (all-time data)
- **Per day**: Can analyze daily improvement over time

## Limitations

1. **First press not counted**: Need 2+ presses of same key
2. **Doesn't measure**: Key release time, total finger movement time
3. **Context dependent**: Speed varies by word, sentence, fatigue
4. **Not a race**: Focus on consistency, not raw speed
