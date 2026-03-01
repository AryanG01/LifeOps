"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-01

"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    -- Core tables
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT NOT NULL UNIQUE,
        display_name TEXT,
        timezone TEXT NOT NULL DEFAULT 'Asia/Singapore',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS sources (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_type TEXT NOT NULL,
        display_name TEXT NOT NULL,
        config_json JSONB NOT NULL DEFAULT '{}',
        last_synced_at TIMESTAMPTZ,
        sync_cursor TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, source_type, display_name)
    );

    CREATE TABLE IF NOT EXISTS raw_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        external_id TEXT,
        payload_json JSONB NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        processed_at TIMESTAMPTZ,
        processing_error TEXT,
        UNIQUE (user_id, source_id, external_id)
    );
    CREATE INDEX IF NOT EXISTS idx_raw_events_user_received
        ON raw_events(user_id, received_at DESC);
    CREATE INDEX IF NOT EXISTS idx_raw_events_unprocessed
        ON raw_events(processed_at) WHERE processed_at IS NULL;

    CREATE TABLE IF NOT EXISTS messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        raw_event_id UUID REFERENCES raw_events(id),
        external_id TEXT,
        sender TEXT NOT NULL,
        title TEXT NOT NULL,
        body_preview TEXT NOT NULL DEFAULT '',
        body_full TEXT,
        message_ts TIMESTAMPTZ NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        dedup_hash TEXT NOT NULL,
        is_canvas BOOLEAN NOT NULL DEFAULT FALSE,
        extra_json JSONB NOT NULL DEFAULT '{}',
        UNIQUE (user_id, dedup_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_messages_user_ts
        ON messages(user_id, message_ts DESC);

    -- LLM-derived tables
    CREATE TABLE IF NOT EXISTS message_summaries (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL DEFAULT 'v1',
        summary_short TEXT NOT NULL,
        summary_long TEXT,
        urgency DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        extraction_failed BOOLEAN NOT NULL DEFAULT FALSE,
        extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (message_id, prompt_version)
    );

    CREATE TABLE IF NOT EXISTS message_labels (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL DEFAULT 'v1',
        label TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL,
        UNIQUE (message_id, prompt_version, label)
    );

    CREATE TABLE IF NOT EXISTS reply_drafts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL DEFAULT 'v1',
        tone TEXT NOT NULL,
        draft_text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'proposed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- LLM audit log
    CREATE TABLE IF NOT EXISTS llm_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL,
        model TEXT NOT NULL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        latency_ms INTEGER,
        validation_passed BOOLEAN NOT NULL,
        validation_error TEXT,
        attempt INTEGER NOT NULL DEFAULT 1,
        ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_llm_runs_message
        ON llm_runs(message_id, prompt_version);

    -- Tasks and reminders
    CREATE TABLE IF NOT EXISTS action_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        message_id UUID REFERENCES messages(id),
        title TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '',
        due_at TIMESTAMPTZ,
        priority INTEGER NOT NULL DEFAULT 50,
        confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        status TEXT NOT NULL DEFAULT 'proposed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_action_items_user_status_due
        ON action_items(user_id, status, due_at);

    CREATE TABLE IF NOT EXISTS reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        action_item_id UUID NOT NULL REFERENCES action_items(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        remind_at TIMESTAMPTZ NOT NULL,
        channel TEXT NOT NULL DEFAULT 'cli',
        status TEXT NOT NULL DEFAULT 'pending',
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (action_item_id, remind_at, channel)
    );
    CREATE INDEX IF NOT EXISTS idx_reminders_user_remind
        ON reminders(user_id, remind_at, status);

    -- PVI tables
    CREATE TABLE IF NOT EXISTS pvi_daily_features (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        tasks_open INTEGER NOT NULL DEFAULT 0,
        tasks_overdue INTEGER NOT NULL DEFAULT 0,
        inbox_unread INTEGER NOT NULL DEFAULT 0,
        incoming_24h INTEGER NOT NULL DEFAULT 0,
        calendar_minutes INTEGER NOT NULL DEFAULT 0,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, date)
    );

    CREATE TABLE IF NOT EXISTS pvi_daily_scores (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        score INTEGER NOT NULL,
        regime TEXT NOT NULL,
        explanation TEXT NOT NULL,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, date)
    );

    CREATE TABLE IF NOT EXISTS policies (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        regime TEXT NOT NULL,
        max_digest_items INTEGER NOT NULL DEFAULT 15,
        escalation_level TEXT NOT NULL DEFAULT 'standard',
        reminder_cadence TEXT NOT NULL DEFAULT 'standard',
        auto_activate BOOLEAN NOT NULL DEFAULT FALSE,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, date)
    );

    -- Digest table
    CREATE TABLE IF NOT EXISTS digests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        content_md TEXT NOT NULL,
        regime TEXT NOT NULL DEFAULT 'normal',
        generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, date)
    );
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS digests CASCADE;
    DROP TABLE IF EXISTS policies CASCADE;
    DROP TABLE IF EXISTS pvi_daily_scores CASCADE;
    DROP TABLE IF EXISTS pvi_daily_features CASCADE;
    DROP TABLE IF EXISTS reminders CASCADE;
    DROP TABLE IF EXISTS action_items CASCADE;
    DROP TABLE IF EXISTS llm_runs CASCADE;
    DROP TABLE IF EXISTS reply_drafts CASCADE;
    DROP TABLE IF EXISTS message_labels CASCADE;
    DROP TABLE IF EXISTS message_summaries CASCADE;
    DROP TABLE IF EXISTS messages CASCADE;
    DROP TABLE IF EXISTS raw_events CASCADE;
    DROP TABLE IF EXISTS sources CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    """)
