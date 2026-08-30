-- Standalone usage tracking: ChatGPT and Gemini image generation that happens
-- OUTSIDE the MCP tool (vendor web apps, personal accounts, other integrations).
-- Run this against the standalone Supabase/Postgres project, not the tool's own.
--
-- Dashboards 2 and 3 compare this against in-tool usage, so the point of this
-- table is the substitution question: is image work running through the tool,
-- or around it?

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.standalone_usage_events (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider text NOT NULL CHECK (provider IN ('chatgpt', 'gemini')),
    user_id text NOT NULL,
    operation text NOT NULL CHECK (operation IN ('generate', 'refine', 'edit', 'variation', 'upscale')),
    created_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL DEFAULT 'manual',
    model text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_by text
);

-- user_id is the designer's work email, lowercased. That is what lets the
-- dashboards join this table to the tool's profiles table and tell
-- "uses ChatGPT directly but never through the tool" from "has not started".
CREATE INDEX IF NOT EXISTS idx_standalone_usage_provider_created_at
    ON public.standalone_usage_events (provider, created_at);
CREATE INDEX IF NOT EXISTS idx_standalone_usage_user_created_at
    ON public.standalone_usage_events (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_standalone_usage_created_at
    ON public.standalone_usage_events (created_at);

-- Bulk CSV imports get re-run. Without a uniqueness key, re-importing last
-- month's export silently doubles every number on the standalone dashboards.
ALTER TABLE public.standalone_usage_events
    ADD COLUMN IF NOT EXISTS dedupe_key text
    GENERATED ALWAYS AS (
        encode(digest(
            provider || '|' || user_id || '|' || operation || '|' ||
            to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '|' ||
            coalesce(model, ''),
            'sha256'), 'hex')
    ) STORED;

CREATE UNIQUE INDEX IF NOT EXISTS uq_standalone_usage_dedupe
    ON public.standalone_usage_events (dedupe_key);

-- ------------------------------------------------------------------
-- Reporting views
-- ------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_standalone_usage_daily AS
SELECT
    date_trunc('day', created_at)::date AS usage_day,
    provider,
    COUNT(*) AS total_actions,
    COUNT(*) FILTER (WHERE operation = 'generate') AS generate_actions,
    COUNT(*) FILTER (WHERE operation IN ('refine', 'edit', 'variation', 'upscale')) AS refine_actions,
    COUNT(DISTINCT user_id) AS active_users
FROM public.standalone_usage_events
GROUP BY 1, 2
ORDER BY 1, 2;

-- Weekly active users must be DISTINCT people across the week. Taking the max
-- of the daily counts undercounts every week where different people show up on
-- different days.
CREATE OR REPLACE VIEW public.v_standalone_usage_weekly AS
SELECT
    date_trunc('week', created_at)::date AS week_start,
    provider,
    COUNT(*) FILTER (WHERE operation = 'generate') AS generate_actions,
    COUNT(*) FILTER (WHERE operation IN ('refine', 'edit', 'variation', 'upscale')) AS refine_actions,
    COUNT(DISTINCT user_id) AS active_users,
    COUNT(*) AS total_actions
FROM public.standalone_usage_events
GROUP BY 1, 2
ORDER BY 1, 2;

CREATE OR REPLACE VIEW public.v_standalone_usage_kpis AS
SELECT
    provider,
    COUNT(*) AS total_actions,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(*) FILTER (WHERE operation = 'generate') AS generate_actions,
    COUNT(*) FILTER (WHERE operation IN ('refine', 'edit', 'variation', 'upscale')) AS refine_actions,
    MIN(created_at) AS first_seen,
    MAX(created_at) AS last_seen
FROM public.standalone_usage_events
GROUP BY provider;

-- Weekly adoption curve per provider: cumulative distinct designers who have
-- ever used that model directly.
CREATE OR REPLACE VIEW public.v_standalone_adoption_curve AS
WITH first_use AS (
    SELECT provider, user_id, MIN(date_trunc('week', created_at)::date) AS first_week
    FROM public.standalone_usage_events
    GROUP BY 1, 2
)
SELECT
    provider,
    first_week AS week_start,
    COUNT(*) AS new_adopters,
    SUM(COUNT(*)) OVER (PARTITION BY provider ORDER BY first_week) AS cumulative_adopters
FROM first_use
GROUP BY 1, 2
ORDER BY 1, 2;

-- ------------------------------------------------------------------
-- Examples
-- ------------------------------------------------------------------
-- Log one direct use:
-- INSERT INTO public.standalone_usage_events (provider, user_id, operation, source, model)
-- VALUES ('chatgpt', 'designer@prezlab.com', 'generate', 'admin_export', 'gpt-image-2');

-- ChatGPT dashboard feed:
-- SELECT * FROM public.v_standalone_usage_daily WHERE provider = 'chatgpt' ORDER BY usage_day;
