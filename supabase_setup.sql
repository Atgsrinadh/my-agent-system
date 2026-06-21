-- Run this SQL in your Supabase dashboard (SQL Editor)
-- Creates all tables needed for the agent system

-- Short-term memory (chat history)
CREATE TABLE IF NOT EXISTS memory (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT DEFAULT 'general',
    task_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory(agent_id);
CREATE INDEX IF NOT EXISTS idx_memory_task ON memory(task_id);

-- Tasks (long-running background jobs)
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL,
    agent_id TEXT DEFAULT 'research',
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    result TEXT,
    steps JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- API usage logs (for dashboard)
CREATE TABLE IF NOT EXISTS api_logs (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    success BOOLEAN DEFAULT true,
    error TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_logs_provider ON api_logs(provider);

-- Runtime settings (API keys, configured from the dashboard — no redeploy needed)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Helper function to get memory size
CREATE OR REPLACE FUNCTION get_memory_size_mb()
RETURNS NUMERIC AS $$
    SELECT ROUND(pg_total_relation_size('memory') / 1024.0 / 1024.0, 2);
$$ LANGUAGE SQL;
