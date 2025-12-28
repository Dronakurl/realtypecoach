# Burst Detection

## Overview

Burst detection identifies continuous periods of typing activity, separating them from rest periods. This allows RealTypeCoach to measure your **sustained typing speed** rather than just individual keystrokes.

## What is a "Burst"?

A **burst** is a continuous sequence of keystrokes without a long pause.

**Example:**
```
User types: "hello world"
Time: 0s    0.1s  0.2s  0.3s  0.5s  0.6s  ...  2.0s  2.1s  2.2s
Keys:  h      e     l     l     o     w     ...  pause  o     r     l     d

Burst: From 'h' to first 'd' (2.2 seconds)
Then pause before next typing...
```

## Burst Timeout

RealTypeCoach uses a **burst timeout** to determine when typing has stopped:

- **Default timeout: 3 seconds** (3000ms)
- If no key press for 3+ seconds → **Burst ends**
- New key press after timeout → **New burst begins**

**Configurable** in settings (`burst_timeout_ms`)

## Why Burst Detection Matters

### 1. Measures Real Typing Speed

Individual keystrokes don't tell the whole story:

```
Without burst detection:
- 60 keystrokes per minute = 60 WPM ( misleading! )

With burst detection:
- Typed 100 chars in 30 seconds of actual typing
- Rest of time: thinking, reading, coffee
- Real burst WPM = 200 WPM (more accurate!)
```

### 2. Identifies Flow State

Bursts represent periods of **focused typing** where you:
- Know what you want to type
- Don't need to think about spelling
- Are "in the zone"

### 3. Distinguishes Typing vs. Other Activities

Separates:
- **Active typing**: Writing code, composing emails
- **Not typing**: Reading, thinking, away from keyboard

## Burst Detection Algorithm

```
1. User presses a key
   ↓
2. If previous burst exists and within timeout:
   → Add to current burst
   ↓
3. Else (timeout exceeded or no burst):
   → Finalize previous burst
   → Start new burst
   ↓
4. Repeat for each key press
```

## Burst Statistics

For each burst, RealTypeCoach tracks:

1. **Start time**: When the first key was pressed
2. **End time**: When the burst ended (timeout)
3. **Duration**: `end_time - start_time` (in milliseconds)
4. **Key count**: Number of keystrokes in the burst
5. **WPM**: Calculated from key count and duration

## High Score Qualification

Not all bursts qualify as "high scores":

**Minimum duration: 10 seconds** (default)

**Rationale:**
- Short bursts (1-2 keystrokes) are unrealistic
- Typing a single word quickly ≠ sustainable speed
- 10+ seconds indicates real typing endurance

**Configurable** in settings (`high_score_min_duration_ms`)

## Example Scenarios

### Scenario 1: Continuous Typing
```
Type a paragraph at 80 WPM for 30 seconds
→ 1 burst, 30 seconds duration, 80 WPM
→ ✓ Qualifies for high score (10s+ duration)
```

### Scenario 2: With Pauses
```
Type sentence, pause to think (2s), continue
→ Still 1 burst (2s < 3s timeout)
→ No split unless pause exceeds 3 seconds
```

### Scenario 3: Short Bursts
```
Type "hello" (0.5s), pause 5s, type "world" (0.5s)
→ 2 separate bursts
→ Neither qualifies for high score (both < 10s)
→ Still tracked for overall statistics
```

## WPM Calculation in Bursts

```
WPM = (keystrokes / 5) / (duration_minutes)

Example:
- Keystrokes: 250
- Duration: 30 seconds = 0.5 minutes
- Words: 250 / 5 = 50 words
- WPM: 50 / 0.5 = 100 WPM
```

**Standard**: 5 characters = 1 word (industry standard)

## Data Storage

Bursts are stored in the `bursts` table:

```sql
CREATE TABLE bursts (
    id INTEGER PRIMARY KEY,
    start_time INTEGER NOT NULL,        -- When burst started (ms since epoch)
    end_time INTEGER NOT NULL,          -- When burst ended (ms since epoch)
    key_count INTEGER NOT NULL,         -- Number of keystrokes
    duration_ms INTEGER NOT NULL,       -- Duration in milliseconds
    avg_wpm REAL,                       -- Words per minute during burst
    qualifies_for_high_score INTEGER    -- 1 if meets minimum duration, else 0
)
```

## Configurable Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `burst_timeout_ms` | 3000ms | Max pause before burst ends |
| `high_score_min_duration_ms` | 10000ms | Min duration for high score |

## Common Questions

**Q: Why is my burst WPM higher than daily average?**
A: Bursts measure active typing only. Daily average includes all pauses.

**Q: What if I type very slowly?**
A: You'll have longer bursts (fewer keystrokes per minute) but still accurate WPM.

**Q: Can I change the timeout?**
A: Yes, in settings. Lower = more bursts, higher = fewer bursts.

**Q: Do short bursts matter?**
A: They contribute to overall statistics but not "personal best" high scores.
