-- PostgreSQL Schema for RealTypeCoach
--
-- This schema matches the SQLite schema used by RealTypeCoach,
-- adapted for PostgreSQL syntax and types.
--
-- Key differences from SQLite:
-- - INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
-- - REAL -> DOUBLE PRECISION
-- - TEXT -> TEXT (same)
-- - INTEGER -> INTEGER or BIGINT for timestamps
-- - Added indexes on frequently queried columns

-- Enable UUID extension (useful for future features)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Bursts table
CREATE TABLE IF NOT EXISTS bursts (
    id SERIAL PRIMARY KEY,
    start_time BIGINT NOT NULL,
    end_time BIGINT NOT NULL,
    key_count INTEGER NOT NULL,
    backspace_count INTEGER DEFAULT 0,
    net_key_count INTEGER DEFAULT 0,
    duration_ms INTEGER NOT NULL,
    avg_wpm DOUBLE PRECISION,
    qualifies_for_high_score INTEGER DEFAULT 0
);

-- Index on start_time for time-series queries
CREATE INDEX IF NOT EXISTS idx_bursts_start_time ON bursts(start_time);

-- Statistics table
CREATE TABLE IF NOT EXISTS statistics (
    keycode INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_press_time DOUBLE PRECISION,
    total_presses INTEGER,
    slowest_ms DOUBLE PRECISION,
    fastest_ms DOUBLE PRECISION,
    last_updated BIGINT,
    PRIMARY KEY (keycode, layout)
);

-- Index for layout-based queries
CREATE INDEX IF NOT EXISTS idx_statistics_layout ON statistics(layout);

-- High scores table
CREATE TABLE IF NOT EXISTS high_scores (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    fastest_burst_wpm DOUBLE PRECISION,
    burst_duration_sec DOUBLE PRECISION,
    burst_key_count INTEGER,
    timestamp BIGINT NOT NULL,
    burst_duration_ms INTEGER
);

-- Index on date for daily queries
CREATE INDEX IF NOT EXISTS idx_high_scores_date ON high_scores(date);

-- Daily summaries table
CREATE TABLE IF NOT EXISTS daily_summaries (
    date TEXT PRIMARY KEY,
    total_keystrokes INTEGER,
    total_bursts INTEGER,
    avg_wpm DOUBLE PRECISION,
    slowest_keycode INTEGER,
    slowest_key_name TEXT,
    total_typing_sec INTEGER,
    summary_sent INTEGER DEFAULT 0
);

-- Word statistics table
CREATE TABLE IF NOT EXISTS word_statistics (
    word TEXT NOT NULL,
    layout TEXT NOT NULL,
    avg_speed_ms_per_letter DOUBLE PRECISION NOT NULL,
    total_letters INTEGER NOT NULL,
    total_duration_ms INTEGER NOT NULL,
    observation_count INTEGER NOT NULL,
    last_seen BIGINT NOT NULL,
    backspace_count INTEGER DEFAULT 0,
    editing_time_ms INTEGER DEFAULT 0,
    PRIMARY KEY (word, layout)
);

-- Index for layout-based queries
CREATE INDEX IF NOT EXISTS idx_word_statistics_layout ON word_statistics(layout);

-- Grant permissions (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO realtypecoach;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO realtypecoach;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO realtypecoach;
