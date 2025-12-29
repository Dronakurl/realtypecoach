# Data Storage

## Overview

RealTypeCoach uses a **SQLite database** to store all typing data locally. This document explains how data is organized, stored, and managed.

## Database Location

```
~/.local/share/realtypecoach/typing_data.db
```

**Example:**
```
/home/username/.local/share/realtypecoach/typing_data.db
```

## Why SQLite?

**Advantages:**
- ✓ Built into Python (no external dependencies)
- ✓ Lightweight and fast
- ✓ Reliable and battle-tested
- ✓ Easy to query with SQL
- ✓ No database server required
- ✓ Single file = easy backup/restore

## Database Schema

### Tables Overview

```
key_events       - Individual keystroke events
bursts          - Typing burst records
statistics      - Per-key statistics (speed data)
high_scores     - Daily high scores
daily_summaries - Aggregated daily statistics
settings        - Application configuration
```

### Table: key_events

Stores individual keystroke events (with selective logging):

```sql
CREATE TABLE key_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keycode INTEGER NOT NULL,          -- Linux evdev keycode
    key_name TEXT NOT NULL,            -- Human-readable (e.g., 'KEY_A')
    timestamp_ms INTEGER NOT NULL,     -- Milliseconds since epoch
    event_type TEXT NOT NULL,          -- 'press' or 'release'
    app_name TEXT,                     -- Application name (if available)
    is_password_field INTEGER DEFAULT 0 -- 1 if password field (always 0)
);
```

**Example data:**
```
id | keycode | key_name | timestamp_ms  | event_type | app_name   | is_password_field
---|---------|----------|---------------|------------|------------|------------------
1  | 30      | KEY_A    | 1735312345678 | press      | kate       | 0
2  | 30      | KEY_A    | 1735312345800 | release    | kate       | 0
3  | 48      | KEY_B    | 1735312346123 | press      | firefox    | 0
```

**Note:** Password field events are never inserted.

#### Selective Logging Behavior

**Important:** RealTypeCoach does NOT log every single keystroke. This is intentional and by design.

**What gets logged:**
- ✓ A subset of key events during active typing
- ✓ Events needed for burst detection and word tracking
- ✓ Sufficient data for statistics and analysis

**What may be skipped:**
- ✗ Some modifier keys (Ctrl, Alt, Shift when used alone)
- ✗ Repetitive key events (auto-repeat)
- ✗ Some non-letter keys when not part of typing patterns
- ✗ Events during very high-frequency typing (performance optimization)

**Why selective logging?**

1. **Performance**: Reduces database I/O during intensive typing
2. **Privacy**: Less data stored = better privacy
3. **Focus**: Captures typing patterns without recording every raw event
4. **Efficiency**: Stores only what's needed for meaningful statistics

**Trade-offs:**
- ✗ Cannot replay exact typing sequence
- ✗ Missing some raw keystroke data
- ✓ All statistics remain accurate
- ✓ Burst detection works correctly
- ✓ Word tracking is preserved

**Example:**
```
You type:        "hello world"
Events logged:   ~5-10 events (not 11+ events)
Accuracy:        Speed, bursts, words still tracked correctly
```

**Note for users:** If you need complete keystroke logging for forensic purposes, this is not the right tool. RealTypeCoach focuses on typing improvement statistics, not comprehensive activity logging.

### Table: bursts

Stores typing bursts (continuous typing periods):

```sql
CREATE TABLE bursts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time INTEGER NOT NULL,        -- Start timestamp (ms)
    end_time INTEGER NOT NULL,          -- End timestamp (ms)
    key_count INTEGER NOT NULL,         -- Number of keystrokes
    duration_ms INTEGER NOT NULL,       -- Duration in milliseconds
    avg_wpm REAL,                       -- Calculated WPM
    qualifies_for_high_score INTEGER DEFAULT 0 -- Boolean: 1 if 10+ seconds
);
```

**Example data:**
```
id | start_time   | end_time     | key_count | duration_ms | avg_wpm | qualifies
---|--------------|--------------|-----------|-------------|---------|----------
1  | 1735312000000| 1735312030000| 250       | 30000       | 100.0   | 1
2  | 1735312100000| 1735312115000| 50        | 15000       | 40.0    | 0
```

### Table: statistics

Stores per-key speed statistics:

```sql
CREATE TABLE statistics (
    keycode INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    layout TEXT NOT NULL,               -- Keyboard layout (us, de, etc.)
    avg_press_time REAL,                -- Average time between presses (ms)
    total_presses INTEGER,              -- Total times pressed
    slowest_ms REAL,                    -- Slowest interval recorded
    fastest_ms REAL,                    -- Fastest interval recorded
    last_updated INTEGER,               -- Last update timestamp (ms)
    PRIMARY KEY (keycode, layout)
);
```

**Example data:**
```
keycode | key_name | layout | avg_press_time | total_presses | slowest_ms | fastest_ms
--------|----------|--------|----------------|---------------|------------|------------
30      | KEY_A    | us     | 145.3          | 1523          | 482.1      | 87.2
48      | KEY_B    | us     | 132.8          | 892           | 391.5      | 76.4
```

**Unique constraint:** One record per key per layout.

### Table: high_scores

Records exceptional typing speeds:

```sql
CREATE TABLE high_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                  -- Date (YYYY-MM-DD)
    fastest_burst_wpm REAL,             -- WPM achieved
    burst_duration_sec REAL,            -- Burst duration in seconds
    burst_key_count INTEGER,             -- Keystrokes in burst
    timestamp INTEGER NOT NULL           -- When achieved (ms since epoch)
);
```

**Example data:**
```
id | date       | fastest_burst_wpm | burst_duration_sec | burst_key_count | timestamp
---|------------|-------------------|-------------------|-----------------|----------
1  | 2025-01-15 | 127.3             | 15.2              | 423             | 1736892345678
2  | 2025-01-15 | 115.8             | 12.8              | 391             | 1736894567890
```

### Table: daily_summaries

Aggregated daily statistics:

```sql
CREATE TABLE daily_summaries (
    date TEXT PRIMARY KEY,               -- Date (YYYY-MM-DD)
    total_keystrokes INTEGER,            -- Total keystrokes that day
    total_bursts INTEGER,                -- Number of bursts
    avg_wpm REAL,                        -- Average WPM for the day
    slowest_keycode INTEGER,             -- Slowest key code
    slowest_key_name TEXT,               -- Slowest key name
    total_typing_sec INTEGER,            -- Total typing time (seconds)
    summary_sent INTEGER DEFAULT 0       -- Was daily summary notification sent?
);
```

**Example data:**
```
date       | total_keystrokes | total_bursts | avg_wpm | slowest_keycode | slowest_key_name | total_typing_sec | summary_sent
-----------|-----------------|--------------|---------|-----------------|------------------|-----------------|-------------
2025-01-15 | 12453           | 87           | 82.3    | 30              | KEY_A            | 925             | 1
2025-01-16 | 8234            | 52           | 78.9    | 57              | KEY_SPACE        | 678             | 0
```

### Table: settings

Application configuration:

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,                -- Setting name
    value TEXT NOT NULL                  -- Setting value (as string)
);
```

**Example data:**
```
key                            | value
-------------------------------|------------------
burst_timeout_ms               | 3000
high_score_min_duration_ms     | 10000
slowest_keys_count             | 10
password_exclusion             | true
```

## Data Retention

### Automatic Cleanup

RealTypeCoach automatically deletes old data:

**Default retention: 90 days**

**What gets deleted:**
- Key events older than 90 days
- Bursts older than 90 days
- Daily summaries older than 90 days

**What's kept:**
- Statistics (all-time key averages)
- High scores (all-time records)
- Settings

**Configurable** via `data_retention_days` setting.

### Why Delete Old Data?

1. **Privacy**: Don't keep data longer than needed
2. **Performance**: Database stays small and fast
3. **Relevance**: Recent data is more useful
4. **Storage**: Minimal disk usage

### Manual Data Deletion

**Delete all data:**
```bash
rm ~/.local/share/realtypecoach/typing_data.db
```

**Or via application:**
- Settings → "Clear Database"
- Deletes everything, starts fresh

## Data Import/Export

### Export to CSV

```python
storage.export_to_csv(
    csv_path='/path/to/export.csv',
    start_date='2025-01-01',
    end_date='2025-01-31'
)
```

**CSV format:**
```csv
timestamp_ms,keycode,key_name,event_type,app_name,is_password_field
1735312345678,30,KEY_A,press,kate,0
1735312345800,30,KEY_A,release,kate,0
...
```

### Backup Database

**Simple backup:**
```bash
cp ~/.local/share/realtypecoach/typing_data.db ~/backup/typing_data_$(date +%Y%m%d).db
```

**Restore:**
```bash
cp ~/backup/typing_data_20250115.db ~/.local/share/realtypecoach/typing_data.db
```

## Database Queries

### Example Queries

**Total keystrokes today:**
```sql
SELECT COUNT(*) FROM key_events
WHERE date(timestamp_ms / 1000, 'unixepoch') = date('now');
```

**Average WPM by day:**
```sql
SELECT date, avg_wpm FROM daily_summaries
ORDER BY date DESC
LIMIT 7;
```

**Slowest keys:**
```sql
SELECT key_name, avg_press_time
FROM statistics
WHERE total_presses >= 2
ORDER BY avg_press_time DESC
LIMIT 10;
```

**Personal best:**
```sql
SELECT date, fastest_burst_wpm
FROM high_scores
ORDER BY fastest_burst_wpm DESC
LIMIT 1;
```

## Performance Considerations

### Indexes

SQLite automatically creates:
- Primary key indexes
- Unique constraint indexes

**Custom indexes** (could be added for performance):
```sql
CREATE INDEX idx_key_events_timestamp ON key_events(timestamp_ms);
CREATE INDEX idx_bursts_start_time ON bursts(start_time);
CREATE INDEX idx_high_scores_date ON high_scores(date);
```

### Database Size

**Typical usage:**
- New database: ~100 KB (empty schema)
- 1 day of heavy typing: ~500 KB
- 1 month of regular use: ~5-10 MB
- 1 year of regular use: ~50-100 MB (with 90-day retention, stays smaller)

**Factors affecting size:**
- Typing volume
- Retention period
- Number of different keys used
- Application switching frequency

### Optimization

**Vacuum** (reclaim space after deletions):
```bash
sqlite3 ~/.local/share/realtypecoach/typing_data.db "VACUUM;"
```

**Analyze** (update query planner statistics):
```bash
sqlite3 ~/.local/share/realtypecoach/typing_data.db "ANALYZE;"
```

## Data Integrity

### Transaction Safety

All database writes use transactions:
```python
with sqlite3.connect(self.db_path) as conn:
    # Multiple operations
    conn.execute(...)
    conn.execute(...)
    conn.commit()  # All or nothing
```

**Protection against:**
- Power loss during write
- Application crash
- Concurrent access issues

### Corruption Recovery

**Check for corruption:**
```bash
sqlite3 ~/.local/share/realtypecoach/typing_data.db "PRAGMA integrity_check;"
```

**Output:** `ok` if database is healthy

**Recover from backup** if corrupted.

## Concurrency

### Single-Instance Design

RealTypeCoach enforces **single instance**:
- PID file: `~/.local/share/realtypecoach/realtypecoach.pid`
- Second instance refuses to start
- Prevents database corruption from concurrent writes

### Locking

SQLite uses **file-level locking**:
- Automatic during writes
- Queue-based for concurrent reads
- No manual locking needed

## Privacy & Security

### File Permissions

Database file permissions:
```
-rw-------  (600)
Owner: Your user
Group: Your group
Others: No access
```

**Protection:**
- Standard Linux file permissions
- Respects encrypted home directories
- No special encryption in database

### Data at Rest

**Not encrypted** within database:
- Relies on file system encryption
- If home directory is encrypted, database is encrypted
- If full disk encryption, database is encrypted

**Why no database encryption?**
- Performance overhead
- Complexity
- Local-only data
- File system encryption is better

## Monitoring Database Health

### Database Size Check

```bash
ls -lh ~/.local/share/realtypecoach/typing_data.db
```

### Row Counts

```sql
-- Total events
SELECT COUNT(*) FROM key_events;

-- Total bursts
SELECT COUNT(*) FROM bursts;

-- Oldest / newest event
SELECT MIN(timestamp_ms), MAX(timestamp_ms) FROM key_events;
```

### Maintenance

**Recommended** (monthly or quarterly):
```bash
# 1. Backup
cp ~/.local/share/realtypecoach/typing_data.db ~/backup/typing_data_$(date +%Y%m%d).db

# 2. Vacuum (reclaim space)
sqlite3 ~/.local/share/realtypecoach/typing_data.db "VACUUM;"

# 3. Analyze (update statistics)
sqlite3 ~/.local/share/realtypecoach/typing_data.db "ANALYZE;"
```

## Troubleshooting

### Database Locked

**Symptom:** "database is locked" error

**Causes:**
- Another instance running
- Crash left PID file
- Other process accessing file

**Solutions:**
```bash
# Kill any running instances
just kill

# Or manually remove PID file
rm ~/.local/share/realtypecoach/realtypecoach.pid
```

### Database Corruption

**Symptom:** "database disk image is malformed"

**Recovery:**
```bash
# 1. Backup (if possible)
cp ~/.local/share/realtypecoach/typing_data.db ~/backup/corrupted_backup.db

# 2. Try to dump data
sqlite3 ~/.local/share/realtypecoach/typing_data.db ".dump" > dump.sql

# 3. Create new database from dump
sqlite3 new_typing_data.db < dump.sql

# 4. Replace (if successful)
mv new_typing_data.db ~/.local/share/realtypecoach/typing_data.db
```

### Performance Issues

**Symptom:** Slow queries, laggy UI

**Solutions:**
```bash
# 1. Delete old data (via app settings)
# 2. Vacuum database
sqlite3 ~/.local/share/realtypecoach/typing_data.db "VACUUM;"
# 3. Check database size (consider reducing retention)
```

## Best Practices

1. **Regular backups**: Before major changes
2. **Monitor size**: Ensure it doesn't grow too large
3. **Export periodically**: Keep CSV exports for analysis
4. **Clean old data**: Use retention settings
5. **Check integrity**: After crashes or power issues
