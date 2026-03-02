"""phase2 tables: calendar_events, focus_sessions

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-02
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS calendar_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
        external_id TEXT NOT NULL,
        title TEXT NOT NULL,
        start_at TIMESTAMPTZ NOT NULL,
        end_at TIMESTAMPTZ NOT NULL,
        location TEXT,
        attendees_json JSONB NOT NULL DEFAULT '[]',
        description TEXT,
        is_all_day BOOLEAN NOT NULL DEFAULT FALSE,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, external_id)
    );

    CREATE TABLE IF NOT EXISTS focus_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ends_at TIMESTAMPTZ NOT NULL,
        ended_early_at TIMESTAMPTZ,
        is_active BOOLEAN NOT NULL DEFAULT TRUE
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS focus_sessions;")
    op.execute("DROP TABLE IF EXISTS calendar_events;")
