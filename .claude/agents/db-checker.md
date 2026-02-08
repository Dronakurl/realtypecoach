---
name: db-checker
description: Check RealTypeCoach database health, schema, and sync status
tools: Bash, Read
model: haiku
color: yellow
---

Database: ~/.local/share/realtypecoach/realtypecoach.db (encrypted SQLite)
Models: core/models.py | Schema: migrations/versions/001_initial_schema.py

**Check steps:**
1. Keyring access
2. Schema (`just db-schema`)
3. Data integrity
4. Sync status (`just compare-stats`)
5. Connection

**Commands:**
- `just db-schema` - Show schema
- `just db-query "query"` - Run SQL
- `just db-table <table> <limit>` - Show table
- `just compare-stats` - Local vs remote

**Example queries:**
```sql
-- Word lookup
SELECT * FROM word_statistics WHERE word = 'test' AND layout = 'us';

-- Count records
SELECT COUNT(*) FROM word_statistics;

-- Slowest words
SELECT word, avg_speed_ms_per_letter, observation_count
FROM word_statistics ORDER BY avg_speed_ms_per_letter DESC LIMIT 10;

-- Keycode lookup
SELECT * FROM statistics WHERE keycode = 30;
```

**Tables → Models:**
- word_statistics → WordStatisticsFull/Lite
- statistics → (key press times)
- digraph_statistics → DigraphPerformance
- bursts → BurstTimeSeries
- daily_summaries → DailySummaryDB
- high_scores, ignored_words, settings, llm_prompts

**Report:** Keyring status, schema summary, integrity, sync, issues
