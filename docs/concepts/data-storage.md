# Data Storage

## Overview

RealTypeCoach uses an **encrypted SQLite database** to store typing statistics locally. This document explains how data is organized and managed.

## Database Location

```
~/.local/share/realtypecoach/typing_data.db
```

**Example:**
```
/home/username/.local/share/realtypecoach/typing_data.db
```

## Security & Privacy

### Encryption

The database is encrypted using **SQLCipher** with keys stored in your system keyring:
- **GNOME Keyring** (gnome-keyring/seahorse)
- **KDE KWallet**

This ensures that:
- ✓ Statistics data is encrypted at rest
- ✓ Only you (with your keyring unlock) can access the data
- ✓ Database file is useless without the encryption key

### No Keystroke History

**Important:** RealTypeCoach does **NOT** store individual keystrokes. No permanent record of what you type is kept.

**What is NOT stored:**
- ✗ Individual keystroke events
- ✗ Typed text or passwords
- ✗ Keystroke history
- ✗ Timings of individual keystrokes

**What IS stored (aggregated statistics only):**
- ✓ WPM (words per minute) per burst
- ✓ Average speed per key
- ✓ Average speed per word
- ✓ Daily summaries (total keystrokes, bursts, typing time)
- ✓ High scores (fastest bursts)

## Database Schema

### Tables Overview

```
bursts              - Typing burst records (WPM, duration, key count)
statistics          - Per-key speed statistics (average press time)
word_statistics     - Per-word speed statistics
high_scores         - Daily high scores
daily_summaries     - Aggregated daily statistics
settings            - Application configuration
```

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
    qualifies_for_high_score INTEGER DEFAULT 0
);
```

**Example data:**
```
id | start_time   | end_time     | key_count | duration_ms | avg_wpm
---|--------------|--------------|-----------|-------------|--------
1  | 1735312000000| 1735312030000| 250       | 30000       | 100.0
2  | 1735312100000| 1735312115000| 50        | 15000       | 40.0
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
30      | a        | us     | 145.3          | 1523          | 482.1      | 87.2
48      | b        | us     | 132.8          | 892           | 391.5      | 76.4
```

### Table: word_statistics

Stores per-word speed statistics:

```sql
CREATE TABLE word_statistics (
    word TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_speed_ms_per_letter REAL NOT NULL,
    total_letters INTEGER NOT NULL,
    total_duration_ms INTEGER NOT NULL,
    observation_count INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    backspace_count INTEGER DEFAULT 0,
    editing_time_ms INTEGER DEFAULT 0,
    PRIMARY KEY (word, layout)
);
```

**Example data:**
```
word   | layout | avg_speed_ms_per_letter | total_letters | observation_count | last_seen
-------|--------|------------------------|---------------|-------------------|----------
hello  | us     | 95.2                   | 50            | 10                | 1736892345678
world  | us     | 102.3                  | 60            | 8                 | 1736894567890
```

### Table: high_scores

Records exceptional typing speeds:

```sql
CREATE TABLE high_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                  -- Date (YYYY-MM-DD)
    fastest_burst_wpm REAL,             -- WPM achieved
    burst_duration_sec REAL,            -- Burst duration in seconds
    burst_key_count INTEGER,             -- Keystrokes in burst
    timestamp INTEGER NOT NULL,          -- When achieved
    burst_duration_ms INTEGER            -- Duration in milliseconds
);
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
    summary_sent INTEGER DEFAULT 0       -- Was notification sent?
);
```

### Table: settings

Application configuration:

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Data Retention

### Automatic Cleanup

RealTypeCoach can automatically delete old data:

**Default retention: 90 days** (configurable)

**What gets deleted:**
- Bursts older than retention period
- Daily summaries older than retention period

**What's kept:**
- Statistics (all-time key averages)
- Word statistics (all-time word averages)
- High scores (all-time records)
- Settings

**Configurable** via `data_retention_days` setting in the application.

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

## Database Size

**Typical usage:**
- New database: ~50 KB (empty schema, encrypted)
- 1 day of heavy typing: ~20-30 KB
- 1 month of regular use: ~500 KB - 1 MB
- 1 year of regular use: ~5-10 MB (with 90-day retention, stays smaller)

**Factors affecting size:**
- Typing volume
- Retention period
- Number of different keys/words used

Much smaller than before since only aggregated statistics are stored, not individual keystrokes.

## Backup & Restore

### Backup Database

```bash
cp ~/.local/share/realtypecoach/typing_data.db ~/backup/typing_data_$(date +%Y%m%d).db
```

### Restore

```bash
cp ~/backup/typing_data_20250115.db ~/.local/share/realtypecoach/typing_data.db
```

**Note:** After restoring, you may need to reinitialize the encryption key if you get a "wrong encryption key" error.

## Encryption Details

### How It Works

1. **Key Generation**: When you first run RealTypeCoach, a random encryption key is generated
2. **Key Storage**: The key is stored in your system keyring (GNOME Keyring or KDE KWallet)
3. **Database Access**: Every time RealTypeCoach starts, it retrieves the key from the keyring
4. **Encryption**: All data is encrypted using SQLCipher (AES-256)

### Key Management

**Encryption key location:**
- **GNOME**: `/org/freedesktop/secrets/collection/login` (via keyring)
- **KDE**: KWallet (`kdewallet`)

**Reinitialize encryption** (WARNING: This deletes existing data):
```bash
rm ~/.local/share/realtypecoach/typing_data.db
```

The next time RealTypeCoach starts, it will create a new database with a new encryption key.

## Monitoring Database Health

### Database Size Check

```bash
ls -lh ~/.local/share/realtypecoach/typing_data.db
```

### Row Counts

```sql
-- Total bursts
SELECT COUNT(*) FROM bursts;

-- Total words tracked
SELECT COUNT(*) FROM word_statistics;

-- Unique keys tracked
SELECT COUNT(*) FROM statistics;
```

## Troubleshooting

### "Database encryption key not found"

This error occurs when the keyring cannot access the encryption key.

**Solutions:**

1. **Check keyring is unlocked:**
   ```bash
   # For GNOME
   loginctl unlock-session

   # For KDE/KWallet
   kwallet-query -l kdewallet
   ```

2. **Verify keyring backend:**
   ```bash
   python3 -c "import keyring; print(keyring.get_keyring())"
   ```

3. **Reinitialize** (WARNING: Deletes all data):
   ```bash
   rm ~/.local/share/realtypecoach/typing_data.db
   ```

### Database Locked

**Symptom:** "database is locked" error

**Causes:**
- Another instance running
- Crash left PID file

**Solutions:**
```bash
# Kill any running instances
just kill

# Or manually remove PID file
rm ~/.local/share/realtypecoach/realtypecoach.pid
```

## Best Practices

1. **Regular backups**: Before major changes or system upgrades
2. **Monitor size**: Ensure it doesn't grow too large
3. **Clean old data**: Use retention settings in the app
4. **Keyring access**: Ensure your keyring is unlocked when logging in
