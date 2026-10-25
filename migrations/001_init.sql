-- 001_init.sql: Initial Core Database Schema and Default Configuration

-- 1. Voice Profiles Table
CREATE TABLE IF NOT EXISTS voice_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    reference_path TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('file', 'mic')),
    original_filename TEXT,
    duration_sec REAL NOT NULL CHECK (duration_sec > 0),
    sample_rate INTEGER NOT NULL,
    quality_score REAL,
    quality_notes TEXT,
    sha256 TEXT NOT NULL,
    consent_confirmed INTEGER NOT NULL CHECK (consent_confirmed = 1),
    consent_confirmed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL CHECK (job_type IN ('text_to_voice', 'recording_to_voice')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    profile_id TEXT REFERENCES voice_profiles(id) ON DELETE SET NULL,
    profile_name_snapshot TEXT NOT NULL,
    input_source TEXT NOT NULL CHECK (input_source IN ('text', 'file', 'mic')),
    input_path TEXT,
    input_text TEXT,
    emotion_mode TEXT CHECK (emotion_mode IN ('auto', 'calm', 'normal', 'expressive') OR emotion_mode IS NULL),
    output_mode TEXT NOT NULL CHECK (output_mode IN ('save', 'play', 'both')),
    output_path TEXT,
    output_sample_rate INTEGER,
    output_duration_sec REAL,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    completed_chunks INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    elapsed_ms INTEGER,
    real_time_factor REAL
);

-- 3. Job Chunks Table
CREATE TABLE IF NOT EXISTS job_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('sentence', 'audio')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'prepared', 'converted', 'failed')),
    text TEXT,
    detected_emotion TEXT,
    expressiveness REAL,
    input_path TEXT,
    output_path TEXT,
    start_sec REAL,
    end_sec REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    UNIQUE (job_id, chunk_index)
);

-- 4. Model Events Table
CREATE TABLE IF NOT EXISTS model_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_key TEXT NOT NULL CHECK (model_key IN ('tts', 'vc', 'emotion')),
    action TEXT NOT NULL CHECK (action IN ('load', 'unload', 'oom')),
    device TEXT NOT NULL,
    vram_free_before_mb INTEGER,
    vram_free_after_mb INTEGER,
    duration_ms INTEGER,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

-- 5. Application Settings Table (Key-Value)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Seed default settings (JSON-encoded values)
INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES
    ('device', '"auto"', '2026-01-01T00:00:00.000Z'),
    ('workers', '0', '2026-01-01T00:00:00.000Z'),
    ('chunk_min_sec', '3.0', '2026-01-01T00:00:00.000Z'),
    ('chunk_max_sec', '5.0', '2026-01-01T00:00:00.000Z'),
    ('crossfade_ms', '30', '2026-01-01T00:00:00.000Z'),
    ('default_output_mode', '"both"', '2026-01-01T00:00:00.000Z'),
    ('keep_warm', 'true', '2026-01-01T00:00:00.000Z'),
    ('vram_budget_mb', '6000', '2026-01-01T00:00:00.000Z'),
    ('sentence_max_chars', '200', '2026-01-01T00:00:00.000Z');
