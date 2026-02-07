# Key Speed Metrics

Tracks the individual speed of each key to identify which keys slow you down.

## Measurement

For each key, measures the **time interval between consecutive presses**:

```
Press 'A' at 1000ms → Press 'A' at 1250ms → Interval = 250ms
```

Average press time = (interval₁ + interval₂ + ... + intervalₙ) / n

**Minimum 2 presses** required per key before calculating average.

## Interpreting the Numbers

| Press Time | Assessment |
|------------|------------|
| 80-120ms | Very fast (touch typist) |
| 120-150ms | Good speed |
| 150-200ms | Average |
| 200-300ms | Slow (rare keys, normal) |
| 300-500ms | Difficulty |
| 500ms+ | Significantly slows typing |

**Common causes of slow keys:**
- Weak fingers (pinky/ring)
- Rarely used symbols (`[`, `\`, `,`)
- Stretches (keys far from home row)
- Physical key issues

## What's Tracked

Only letter keys (a-z) and common umlauts (ä, ö, ü, ß) are shown in the UI. Other keys are tracked but not displayed.

Separate statistics per keyboard layout (US, DE, DVORAK, etc.) since the same keycode can represent different characters.

## Data Storage

Stored in `statistics` table:

```sql
CREATE TABLE statistics (
    keycode INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_press_time REAL,        -- Average time between presses (ms)
    total_presses INTEGER,       -- Total times pressed
    slowest_ms REAL,            -- Slowest interval
    fastest_ms REAL,            -- Fastest interval
    last_updated INTEGER,
    PRIMARY KEY (keycode, layout)
)
```
