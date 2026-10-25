-- 002_indexes.sql: Performance Indexes for Job and Event Queries

CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_job_chunks_job ON job_chunks(job_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_model_events_created ON model_events(created_at);
