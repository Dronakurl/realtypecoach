# Data Storage

RealTypeCoach uses an **encrypted SQLite database** (SQLCipher) to store typing statistics locally at `~/.local/share/realtypecoach/typing_data.db`.

## Privacy

**No keystroke history is stored.** Only aggregated statistics:
- WPM per burst (not individual keystrokes)
- Average speed per key/word/digraph
- Daily summaries
- High scores

Encryption keys are stored in your system keyring (GNOME Keyring, KDE KWallet, or other keyring backends).

## Schema

### bursts

Continuous typing periods (3+ second pause ends a burst):

```sql
CREATE TABLE bursts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time INTEGER NOT NULL UNIQUE,     -- Millisecond timestamp
    end_time INTEGER NOT NULL,
    key_count INTEGER NOT NULL,
    backspace_count INTEGER DEFAULT 0,      -- Backspace keystrokes
    net_key_count INTEGER DEFAULT 0,        -- key_count - backspace_count
    duration_ms INTEGER NOT NULL,
    avg_wpm REAL,
    qualifies_for_high_score INTEGER DEFAULT 0
)
```

### statistics

Per-key speed averages:

```sql
CREATE TABLE statistics (
    keycode INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_press_time REAL,
    total_presses INTEGER,
    slowest_ms REAL,
    fastest_ms REAL,
    last_updated INTEGER,
    PRIMARY KEY (keycode, layout)
)
```

### digraph_statistics

Two-key combination speeds (pairs):

```sql
CREATE TABLE digraph_statistics (
    first_keycode INTEGER NOT NULL,
    second_keycode INTEGER NOT NULL,
    first_key TEXT NOT NULL,
    second_key TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_interval_ms REAL NOT NULL,
    total_sequences INTEGER NOT NULL DEFAULT 1,
    slowest_ms REAL,
    fastest_ms REAL,
    last_updated INTEGER,
    PRIMARY KEY (first_keycode, second_keycode, layout)
)
```

### word_statistics

Per-word typing speeds:

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
)
```

### ignored_words

Hashes of excluded words (privacy-focused):

```sql
CREATE TABLE ignored_words (
    word_hash TEXT PRIMARY KEY,   -- BLAKE2b-256 hash (64 hex chars)
    added_at INTEGER NOT NULL
)
```

### high_scores

Daily best bursts:

```sql
CREATE TABLE high_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    fastest_burst_wpm REAL,
    burst_duration_sec REAL,
    burst_key_count INTEGER,
    timestamp INTEGER NOT NULL UNIQUE,
    burst_duration_ms INTEGER
)
```

### daily_summaries

Aggregated daily stats:

```sql
CREATE TABLE daily_summaries (
    date TEXT PRIMARY KEY,
    total_keystrokes INTEGER,
    total_bursts INTEGER,
    avg_wpm REAL,
    slowest_keycode INTEGER,
    slowest_key_name TEXT,
    total_typing_sec INTEGER,
    summary_sent INTEGER DEFAULT 0
)
```

### settings

Configuration sync between machines:

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
)
```

## Data Retention

Default: **90 days** (`data_retention_days` setting). Old bursts and daily summaries are auto-deleted. Statistics (key/word/digraph averages) and high scores are kept indefinitely.

## Encryption

SQLCipher with AES-256. Keys stored in system keyring. Database file is unreadable without the key.

## Database Size

Typical: ~500 KB - 1 MB per month with retention enabled.
