# Clawdbot Life Ops + PVI — Phase 1 MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a personal ops bot that ingests Gmail + Canvas (NUS) emails, runs LLM extraction, manages tasks/reminders, computes PVI, generates a daily digest, and pushes reminders via Telegram — backed by Postgres with a CLI-first interface.

**Architecture:** Event-sourced pipeline — raw_events are immutable; all derived data (messages, tasks, digests) is replayable. Background jobs use APScheduler + Postgres (no Redis). FastAPI is localhost-only. Telegram bot runs in the worker for push delivery.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, APScheduler, Typer (CLI), keyring, google-auth-oauthlib, python-telegram-bot, structlog, pytest

**Key decisions from brainstorming:**
- DB: Postgres-only via Docker (production parity; tests use `clawdbot_test` DB)
- Canvas: NUS-specific patterns (`canvas.nus.edu.sg`, NUS course codes `[A-Z]{2,3}\d{4}[A-Z]?`)
- LLM scope: configurable per Gmail label filter (default: `INBOX + UNREAD`)
- Telegram: Phase 1 (not deferred) — digest at 7am + reminder push
- LLM audit: `llm_runs` table included in schema

---

## PROGRESS TRACKER

- [x] Task 1: Monorepo scaffold + pyproject files
- [x] Task 2: docker-compose + Settings (incl. Telegram + LLM filter config)
- [x] Task 3: Alembic migrations (all tables incl. llm_runs)
- [x] Task 4: SQLAlchemy ORM models (incl. LLMRun)
- [x] Task 5: Pydantic schemas (LLM extraction + API)
- [x] Task 6: Token storage abstraction — commit 3c53bf9
- [x] Task 7: Gmail OAuth + polling connector (with backoff) — commit c5fa3fd
- [x] Task 8: Canvas email-bridge parser (NUS-tuned) — commit 6682abc
- [x] Task 9: Normalizer + dedup pipeline — commit b5e9e99
- [x] Task 10: LLM extractor with retry + llm_runs audit — commit 94cd166
- [x] Task 11: Task/reminder engine — commit 6b9d9ec
- [x] Task 12: PVI engine — commit c427c35
- [x] Task 13: Digest generator — commit c427c35
- [x] Task 14: FastAPI app + endpoints — commit 68c942b
- [x] Task 15: Worker/scheduler (APScheduler) — commit 0871068
- [x] Task 16: CLI (all claw commands) — commit e5c68db
- [x] Task 17: Unit tests (43/43 passing) — commit 5627554 + fixes 55f559a
- [x] Task 18: Integration tests + logging + Dockerfiles — commit 4e482f7
- [x] POST-MVP: Telegram delivery (send_message, send_digest, claw telegram) — commit 5b0611b
- [x] POST-MVP: Gemini + Anthropic dual provider, claw llm status/use/test — commit dadbfc6
- [x] POST-MVP: Bug fixes (savepoint rollback, sessionmaker singleton) — commit ffa2c03

## ALL MVP TASKS COMPLETE ✓

## NEXT SESSION — Continue building:
- [x] claw status — system health overview (DB, Gmail, LLM, Telegram, pending counts)
- [x] claw reminders list — view upcoming pending reminders
- [x] Remove legacy llm_model field from config.py
- [x] claw worker start — start background scheduler from CLI
- [x] End-to-end test with real Gmail + Gemini API (pipeline validated)

## Phase 2 Plan
See: docs/plans/2026-03-02-clawdbot-phase2.md

---

## Task 1: Monorepo Scaffold + pyproject Files

**Files to Create:**
- `pyproject.toml` (root workspace)
- `apps/api/pyproject.toml`
- `apps/worker/pyproject.toml`
- `packages/core/pyproject.toml`
- `packages/connectors/pyproject.toml`
- `packages/cli/pyproject.toml`
- `packages/core/src/core/__init__.py`
- `packages/connectors/src/connectors/__init__.py`
- `packages/cli/src/cli/__init__.py`
- `apps/api/src/api/__init__.py`
- `apps/worker/src/worker/__init__.py`

**Step 1: Create root directory structure**
```bash
mkdir -p apps/api/src/api
mkdir -p apps/worker/src/worker
mkdir -p packages/core/src/core
mkdir -p packages/connectors/src/connectors
mkdir -p packages/cli/src/cli
mkdir -p infra/alembic/versions
mkdir -p infra/scripts
mkdir -p tests/unit
mkdir -p tests/integration
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

**Step 2: Write root pyproject.toml**
```toml
# pyproject.toml
[tool.uv.workspace]
members = ["apps/*", "packages/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
```

**Step 3: Write packages/core/pyproject.toml**
```toml
[project]
name = "core"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "psycopg2-binary>=2.9",
    "structlog>=24.0",
    "keyring>=24.0",
    "anthropic>=0.25",
    "python-dateutil>=2.8",
    "pytz>=2024.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/core"]
```

**Step 4: Write packages/connectors/pyproject.toml**
```toml
[project]
name = "connectors"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "core",
    "google-auth>=2.29",
    "google-auth-oauthlib>=1.2",
    "google-api-python-client>=2.125",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/connectors"]
```

**Step 5: Write packages/cli/pyproject.toml**
```toml
[project]
name = "cli"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "core",
    "connectors",
    "typer>=0.12",
    "rich>=13.0",
    "httpx>=0.27",
]

[project.scripts]
claw = "cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/cli"]
```

**Step 6: Write apps/api/pyproject.toml**
```toml
[project]
name = "api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "core",
    "connectors",
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "python-multipart>=0.0.9",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/api"]
```

**Step 7: Write apps/worker/pyproject.toml**
```toml
[project]
name = "worker"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "core",
    "connectors",
    "apscheduler>=3.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/worker"]
```

**Step 8: Write root requirements file for dev**
```toml
# requirements-dev.txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.14
httpx>=0.27
```

**Step 9: Create all __init__.py files**
```bash
touch packages/core/src/core/__init__.py
touch packages/connectors/src/connectors/__init__.py
touch packages/cli/src/cli/__init__.py
touch apps/api/src/api/__init__.py
touch apps/worker/src/worker/__init__.py
```

**Step 10: Commit**
```bash
git add .
git commit -m "feat: monorepo scaffold with pyproject files"
```

---

## Task 2: docker-compose + Settings

**Files to Create:**
- `infra/docker-compose.yml`
- `packages/core/src/core/config.py`
- `.env.example`

**Step 1: Write docker-compose.yml**
```yaml
# infra/docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: clawdbot
      POSTGRES_PASSWORD: clawdbot
      POSTGRES_DB: clawdbot
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U clawdbot"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: ..
      dockerfile: apps/api/Dockerfile
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy

  worker:
    build:
      context: ..
      dockerfile: apps/worker/Dockerfile
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:
```

**Step 2: Write core/config.py**
```python
# packages/core/src/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql://clawdbot:clawdbot@localhost:5432/clawdbot"
    )
    anthropic_api_key: str = Field(default="")
    llm_model: str = Field(default="claude-sonnet-4-6")
    llm_mode: str = Field(default="enabled")  # enabled | disabled

    # Privacy
    privacy_store_full_bodies: bool = Field(default=True)
    privacy_redact_emails: bool = Field(default=False)

    # API
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)

    # User
    user_timezone: str = Field(default="Asia/Singapore")
    default_user_id: str = Field(
        default="00000000-0000-0000-0000-000000000001"
    )

    # Gmail OAuth
    gmail_credentials_path: str = Field(default="~/.config/clawdbot/gmail_credentials.json")
    gmail_token_service: str = Field(default="clawdbot-gmail")
    gmail_poll_interval_minutes: int = Field(default=15)
    gmail_max_results: int = Field(default=50)

    # LLM
    llm_prompt_version: str = Field(default="v1")


def get_settings() -> Settings:
    return Settings()
```

**Step 3: Write .env.example**
```bash
DATABASE_URL=postgresql://clawdbot:clawdbot@localhost:5432/clawdbot
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODE=enabled
PRIVACY_STORE_FULL_BODIES=true
USER_TIMEZONE=Asia/Singapore
```

**Step 4: Commit**
```bash
git add .
git commit -m "feat: docker-compose and settings config"
```

---

## Task 3: Alembic Migrations (All Tables)

**Files to Create:**
- `infra/alembic.ini`
- `infra/alembic/env.py`
- `infra/alembic/versions/0001_initial_schema.py`

**Step 1: Initialize Alembic**
```bash
cd infra && alembic init alembic
```

**Step 2: Write alembic/env.py**
```python
# infra/alembic/env.py
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../packages/core/src"))

from core.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = None  # Using raw DDL migrations


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 3: Write initial migration**
```python
# infra/alembic/versions/0001_initial_schema.py
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    CREATE TABLE users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT NOT NULL UNIQUE,
        display_name TEXT,
        timezone TEXT NOT NULL DEFAULT 'Asia/Singapore',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE sources (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_type TEXT NOT NULL,  -- 'gmail', 'canvas_bridge'
        display_name TEXT NOT NULL,
        config_json JSONB NOT NULL DEFAULT '{}',
        last_synced_at TIMESTAMPTZ,
        sync_cursor TEXT,  -- historyId for gmail
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, source_type, display_name)
    );

    CREATE TABLE raw_events (
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
    CREATE INDEX idx_raw_events_user_received ON raw_events(user_id, received_at DESC);
    CREATE INDEX idx_raw_events_unprocessed ON raw_events(processed_at) WHERE processed_at IS NULL;

    CREATE TABLE messages (
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
    CREATE INDEX idx_messages_user_ts ON messages(user_id, message_ts DESC);
    CREATE INDEX idx_messages_unextracted ON messages(id) WHERE id NOT IN (
        SELECT message_id FROM message_summaries
    );

    CREATE TABLE message_summaries (
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

    CREATE TABLE message_labels (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL DEFAULT 'v1',
        label TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL,
        UNIQUE (message_id, prompt_version, label)
    );

    CREATE TABLE reply_drafts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL DEFAULT 'v1',
        tone TEXT NOT NULL,
        draft_text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'proposed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE action_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        message_id UUID REFERENCES messages(id),
        title TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '',
        due_at TIMESTAMPTZ,
        priority INTEGER NOT NULL DEFAULT 50,
        confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        status TEXT NOT NULL DEFAULT 'proposed',  -- proposed|active|done|dismissed
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX idx_action_items_user_status_due ON action_items(user_id, status, due_at);

    CREATE TABLE reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        action_item_id UUID NOT NULL REFERENCES action_items(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        remind_at TIMESTAMPTZ NOT NULL,
        channel TEXT NOT NULL DEFAULT 'cli',
        status TEXT NOT NULL DEFAULT 'pending',  -- pending|sent|snoozed|cancelled
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (action_item_id, remind_at, channel)
    );
    CREATE INDEX idx_reminders_user_remind ON reminders(user_id, remind_at, status);

    CREATE TABLE pvi_daily_features (
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

    CREATE TABLE pvi_daily_scores (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        score INTEGER NOT NULL,
        regime TEXT NOT NULL,  -- overloaded|recovery|normal|peak
        explanation TEXT NOT NULL,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, date)
    );

    CREATE TABLE policies (
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

    CREATE TABLE digests (
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
    DROP TABLE IF EXISTS reply_drafts CASCADE;
    DROP TABLE IF EXISTS message_labels CASCADE;
    DROP TABLE IF EXISTS message_summaries CASCADE;
    DROP TABLE IF EXISTS messages CASCADE;
    DROP TABLE IF EXISTS raw_events CASCADE;
    DROP TABLE IF EXISTS sources CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    """)
```

**Step 4: Verify migrations run**
```bash
cd /path/to/project
docker-compose -f infra/docker-compose.yml up -d db
cd infra && alembic upgrade head
```
Expected: no errors, all tables created.

**Step 5: Commit**
```bash
git add .
git commit -m "feat: alembic initial schema migration with all core tables"
```

---

## Task 4: SQLAlchemy ORM Models

**Files to Create:**
- `packages/core/src/core/db/__init__.py`
- `packages/core/src/core/db/engine.py`
- `packages/core/src/core/db/models.py`

**Step 1: Write engine.py**
```python
# packages/core/src/core/db/engine.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from core.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=None)


@contextmanager
def get_db() -> Session:
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**Step 2: Write models.py**
```python
# packages/core/src/core/db/models.py
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float,
    DateTime, Date, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email = Column(Text, nullable=False, unique=True)
    display_name = Column(Text)
    timezone = Column(Text, nullable=False, default="Asia/Singapore")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Source(Base):
    __tablename__ = "sources"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    source_type = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    config_json = Column(JSON, nullable=False, default=dict)
    last_synced_at = Column(DateTime(timezone=True))
    sync_cursor = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RawEvent(Base):
    __tablename__ = "raw_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    source_id = Column(UUID(as_uuid=False), ForeignKey("sources.id"), nullable=False)
    external_id = Column(Text)
    payload_json = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at = Column(DateTime(timezone=True))
    processing_error = Column(Text)


class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    source_id = Column(UUID(as_uuid=False), ForeignKey("sources.id"), nullable=False)
    raw_event_id = Column(UUID(as_uuid=False), ForeignKey("raw_events.id"))
    external_id = Column(Text)
    sender = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    body_preview = Column(Text, nullable=False, default="")
    body_full = Column(Text)
    message_ts = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    dedup_hash = Column(Text, nullable=False)
    is_canvas = Column(Boolean, nullable=False, default=False)
    extra_json = Column(JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint("user_id", "dedup_hash"),)


class MessageSummary(Base):
    __tablename__ = "message_summaries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    summary_short = Column(Text, nullable=False)
    summary_long = Column(Text)
    urgency = Column(Float, nullable=False, default=0.5)
    extraction_failed = Column(Boolean, nullable=False, default=False)
    extracted_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("message_id", "prompt_version"),)


class MessageLabel(Base):
    __tablename__ = "message_labels"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    label = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("message_id", "prompt_version", "label"),)


class ReplyDraft(Base):
    __tablename__ = "reply_drafts"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    tone = Column(Text, nullable=False)
    draft_text = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="proposed")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ActionItem(Base):
    __tablename__ = "action_items"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id"))
    title = Column(Text, nullable=False)
    details = Column(Text, nullable=False, default="")
    due_at = Column(DateTime(timezone=True))
    priority = Column(Integer, nullable=False, default=50)
    confidence = Column(Float, nullable=False, default=0.5)
    status = Column(Text, nullable=False, default="proposed")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    action_item_id = Column(UUID(as_uuid=False), ForeignKey("action_items.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    channel = Column(Text, nullable=False, default="cli")
    status = Column(Text, nullable=False, default="pending")
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("action_item_id", "remind_at", "channel"),)


class PVIDailyFeature(Base):
    __tablename__ = "pvi_daily_features"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    tasks_open = Column(Integer, nullable=False, default=0)
    tasks_overdue = Column(Integer, nullable=False, default=0)
    inbox_unread = Column(Integer, nullable=False, default=0)
    incoming_24h = Column(Integer, nullable=False, default=0)
    calendar_minutes = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "date"),)


class PVIDailyScore(Base):
    __tablename__ = "pvi_daily_scores"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    score = Column(Integer, nullable=False)
    regime = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "date"),)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    regime = Column(Text, nullable=False)
    max_digest_items = Column(Integer, nullable=False, default=15)
    escalation_level = Column(Text, nullable=False, default="standard")
    reminder_cadence = Column(Text, nullable=False, default="standard")
    auto_activate = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "date"),)


class Digest(Base):
    __tablename__ = "digests"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    content_md = Column(Text, nullable=False)
    regime = Column(Text, nullable=False, default="normal")
    generated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "date"),)
```

**Step 3: Commit**
```bash
git add .
git commit -m "feat: SQLAlchemy ORM models for all core tables"
```

---

## Task 5: Pydantic Schemas (LLM Extraction + API)

**Files to Create:**
- `packages/core/src/core/schemas/__init__.py`
- `packages/core/src/core/schemas/llm.py`
- `packages/core/src/core/schemas/api.py`

**Step 1: Write llm.py (strict validation)**
```python
# packages/core/src/core/schemas/llm.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime


class Label(BaseModel):
    model_config = {"extra": "forbid"}
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class ActionItemSchema(BaseModel):
    model_config = {"extra": "forbid"}
    title: str
    details: str
    due_at: Optional[datetime] = None
    priority: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)


class ReplyDraftSchema(BaseModel):
    model_config = {"extra": "forbid"}
    tone: str
    draft_text: str


class Evidence(BaseModel):
    model_config = {"extra": "forbid"}
    due_date_evidence: Optional[str] = None
    source_url: Optional[str] = None


class ExtractionResult(BaseModel):
    model_config = {"extra": "forbid"}
    labels: list[Label]
    summary_short: str
    summary_long: Optional[str] = None
    action_items: list[ActionItemSchema]
    reply_drafts: list[ReplyDraftSchema] = Field(default_factory=list)
    urgency: float = Field(ge=0.0, le=1.0)
    evidence: Optional[Evidence] = None
```

**Step 2: Write api.py (response schemas)**
```python
# packages/core/src/core/schemas/api.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date


class MessageOut(BaseModel):
    id: str
    source_type: str
    sender: str
    title: str
    body_preview: str
    message_ts: datetime
    summary_short: Optional[str] = None
    urgency: Optional[float] = None
    is_canvas: bool
    action_required: bool = False

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    title: str
    details: str
    due_at: Optional[datetime] = None
    priority: int
    confidence: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PVIOut(BaseModel):
    date: date
    score: int
    regime: str
    explanation: str
    features: dict
    policy: dict


class DigestOut(BaseModel):
    date: date
    content_md: str
    regime: str
    generated_at: datetime
```

**Step 3: Commit**
```bash
git add .
git commit -m "feat: pydantic v2 schemas for LLM extraction and API responses"
```

---

## Task 6: Token Storage Abstraction

**Files to Create:**
- `packages/core/src/core/tokens.py`

**Step 1: Write tokens.py**
```python
# packages/core/src/core/tokens.py
"""Secure token storage using OS keychain (keyring) with file fallback."""
import json
import os
import structlog
from pathlib import Path

log = structlog.get_logger()

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


def _fallback_path(service: str, username: str) -> Path:
    base = Path.home() / ".config" / "clawdbot" / "tokens"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{service}_{username}.json"


def store_token(service: str, username: str, token_data: dict) -> None:
    """Store token data securely. Never logs token values."""
    serialized = json.dumps(token_data)
    if _KEYRING_AVAILABLE:
        keyring.set_password(service, username, serialized)
        log.info("token_stored", service=service, username=username, backend="keyring")
    else:
        path = _fallback_path(service, username)
        path.write_text(serialized)
        path.chmod(0o600)
        log.info("token_stored", service=service, username=username, backend="file")


def get_token(service: str, username: str) -> dict | None:
    """Retrieve token data. Returns None if not found."""
    if _KEYRING_AVAILABLE:
        value = keyring.get_password(service, username)
        if value:
            return json.loads(value)
        return None
    else:
        path = _fallback_path(service, username)
        if path.exists():
            return json.loads(path.read_text())
        return None


def delete_token(service: str, username: str) -> None:
    if _KEYRING_AVAILABLE:
        try:
            keyring.delete_password(service, username)
        except Exception:
            pass
    else:
        path = _fallback_path(service, username)
        if path.exists():
            path.unlink()
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: secure token storage with keyring + file fallback"
```

---

## Task 7: Gmail OAuth + Polling Connector

**Files to Create:**
- `packages/connectors/src/connectors/gmail/__init__.py`
- `packages/connectors/src/connectors/gmail/auth.py`
- `packages/connectors/src/connectors/gmail/poller.py`

**Step 1: Write auth.py**
```python
# packages/connectors/src/connectors/gmail/auth.py
import json
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from core.tokens import store_token, get_token
from core.config import get_settings
import structlog

log = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
]

SERVICE_NAME = "clawdbot-gmail"
TOKEN_USERNAME = "default"


def get_credentials() -> Credentials:
    """Get valid Gmail credentials, refreshing if needed."""
    settings = get_settings()
    token_data = get_token(SERVICE_NAME, TOKEN_USERNAME)

    creds = None
    if token_data:
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
        log.info("gmail_token_refreshed")

    if not creds or not creds.valid:
        raise ValueError("No valid Gmail credentials. Run: claw connect gmail")

    return creds


def run_oauth_flow(credentials_file: str) -> Credentials:
    """Run OAuth installed-app flow with local redirect."""
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _save_credentials(creds)
    log.info("gmail_oauth_complete")
    return creds


def _save_credentials(creds: Credentials) -> None:
    """Save credentials without logging secret values."""
    store_token(SERVICE_NAME, TOKEN_USERNAME, {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    })
```

**Step 2: Write poller.py**
```python
# packages/connectors/src/connectors/gmail/poller.py
import base64
import hashlib
from datetime import datetime, timezone
from googleapiclient.discovery import build
from core.config import get_settings
from core.db.engine import get_db
from core.db.models import User, Source, RawEvent
from connectors.gmail.auth import get_credentials
import structlog

log = structlog.get_logger()


def _get_service():
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode_body(payload: dict) -> str:
    """Extract body text from Gmail payload."""
    body = ""
    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break
    return body[:10000]  # Cap at 10k chars


def _extract_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def poll_gmail(user_id: str, source_id: str) -> int:
    """Poll Gmail for new messages. Returns count of new raw_events inserted."""
    settings = get_settings()
    service = _get_service()

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        existing_ids = {
            r.external_id for r in db.query(RawEvent.external_id)
            .filter_by(user_id=user_id, source_id=source_id)
            .filter(RawEvent.external_id.isnot(None))
        }

    # List message IDs
    fmt = "full" if settings.privacy_store_full_bodies else "metadata"
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=settings.gmail_max_results,
    ).execute()

    messages = results.get("messages", [])
    inserted = 0

    for msg_stub in messages:
        msg_id = msg_stub["id"]
        if msg_id in existing_ids:
            continue

        # Fetch full message
        msg = service.users().messages().get(
            userId="me", id=msg_id, format=fmt
        ).execute()

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        raw_payload = {
            "gmail_id": msg_id,
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "label_ids": msg.get("labelIds", []),
            "internal_date": msg.get("internalDate"),
            "sender": _extract_header(headers, "From"),
            "subject": _extract_header(headers, "Subject"),
            "body_text": _decode_body(payload) if settings.privacy_store_full_bodies else "",
            "format": fmt,
        }

        with get_db() as db:
            event = RawEvent(
                user_id=user_id,
                source_id=source_id,
                external_id=msg_id,
                payload_json=raw_payload,
            )
            db.add(event)
            try:
                db.commit()
                inserted += 1
                log.info("raw_event_inserted", external_id=msg_id, user_id=user_id)
            except Exception:
                db.rollback()  # Duplicate — already exists

    log.info("gmail_poll_complete", inserted=inserted, user_id=user_id)
    return inserted
```

**Step 3: Commit**
```bash
git add .
git commit -m "feat: Gmail OAuth flow and polling connector"
```

---

## Task 8: Canvas Email-Bridge Parser

**Files to Create:**
- `packages/connectors/src/connectors/canvas/__init__.py`
- `packages/connectors/src/connectors/canvas/parser.py`

**Step 1: Write parser.py**
```python
# packages/connectors/src/connectors/canvas/parser.py
"""
Canvas email-bridge parser.
Detects Canvas notification emails in Gmail and extracts structured fields.
"""
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


CANVAS_SENDER_PATTERNS = [
    r"instructure\.com",
    r"canvas\..*\.edu",
    r"notifications@.*canvas",
    r"no-reply@.*instructure",
]

CANVAS_SUBJECT_PATTERNS = [
    r"assignment",
    r"announcement",
    r"canvas",
    r"due",
    r"submission",
    r"course",
    r"quiz",
    r"grade",
]

DUE_DATE_PATTERNS = [
    r"[Dd]ue[:\s]+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}[\s,]+\d{1,2}:\d{2}\s*[APap][Mm]?)",
    r"[Dd]ue[:\s]+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
    r"[Dd]ue[:\s]+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
    r"[Dd]ue\s+(?:by\s+)?([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?)",
    r"(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}\s*[APap][Mm]",
]

COURSE_CODE_PATTERNS = [
    r"\b([A-Z]{2,4}\s?\d{3,4}[A-Z]?)\b",
    r"course[:\s]+([A-Z]{2,4}\s?\d{3,4})",
]

URL_PATTERN = re.compile(
    r"https?://[^\s<>\"]+(?:assignments|courses|quizzes|announcements)[^\s<>\"]*"
)


@dataclass
class CanvasParseResult:
    is_canvas: bool
    course_code: Optional[str]
    course_name: Optional[str]
    assignment_title: Optional[str]
    due_at_raw: Optional[str]
    canvas_url: Optional[str]
    canvas_type: Optional[str]  # assignment|announcement|quiz|grade


def is_canvas_email(sender: str, subject: str, body: str) -> bool:
    sender_match = any(re.search(p, sender, re.IGNORECASE) for p in CANVAS_SENDER_PATTERNS)
    subject_match = any(re.search(p, subject, re.IGNORECASE) for p in CANVAS_SUBJECT_PATTERNS)
    body_match = "canvas" in body.lower() or "instructure" in body.lower()
    return sender_match or (subject_match and body_match)


def parse_canvas_email(sender: str, subject: str, body: str) -> CanvasParseResult:
    if not is_canvas_email(sender, subject, body):
        return CanvasParseResult(
            is_canvas=False, course_code=None, course_name=None,
            assignment_title=None, due_at_raw=None, canvas_url=None, canvas_type=None
        )

    full_text = f"{subject}\n{body}"

    # Detect type
    canvas_type = None
    if re.search(r"announcement", full_text, re.IGNORECASE):
        canvas_type = "announcement"
    elif re.search(r"quiz|exam", full_text, re.IGNORECASE):
        canvas_type = "quiz"
    elif re.search(r"grade|graded|scored", full_text, re.IGNORECASE):
        canvas_type = "grade"
    elif re.search(r"assignment|submission|due", full_text, re.IGNORECASE):
        canvas_type = "assignment"

    # Extract course code
    course_code = None
    for pattern in COURSE_CODE_PATTERNS:
        m = re.search(pattern, full_text)
        if m:
            course_code = m.group(1).strip()
            break

    # Extract due date
    due_at_raw = None
    for pattern in DUE_DATE_PATTERNS:
        m = re.search(pattern, full_text)
        if m:
            due_at_raw = m.group(1).strip()
            break

    # Extract URL
    url_match = URL_PATTERN.search(body)
    canvas_url = url_match.group(0) if url_match else None

    # Extract assignment title from subject
    assignment_title = None
    # Common patterns: "Assignment due: <title>", "Submission: <title>"
    for prefix in [r"[Aa]ssignment[:\s]+", r"[Ss]ubmission[:\s]+", r"[Qq]uiz[:\s]+"]:
        m = re.search(prefix + r"(.+?)(?:\s+[Dd]ue|\s*$)", subject)
        if m:
            assignment_title = m.group(1).strip()
            break
    if not assignment_title and subject:
        assignment_title = subject.strip()

    return CanvasParseResult(
        is_canvas=True,
        course_code=course_code,
        course_name=None,  # Not always present in email
        assignment_title=assignment_title,
        due_at_raw=due_at_raw,
        canvas_url=canvas_url,
        canvas_type=canvas_type,
    )
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: Canvas email-bridge parser with course/due-date/URL extraction"
```

---

## Task 9: Normalizer + Dedup Pipeline

**Files to Create:**
- `packages/core/src/core/pipeline/__init__.py`
- `packages/core/src/core/pipeline/normalizer.py`

**Step 1: Write normalizer.py**
```python
# packages/core/src/core/pipeline/normalizer.py
import hashlib
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from core.db.engine import get_db
from core.db.models import RawEvent, Message
from connectors.canvas.parser import parse_canvas_email
import structlog

log = structlog.get_logger()


def _compute_dedup_hash(user_id: str, external_id: str, sender: str, subject: str) -> str:
    key = f"{user_id}:{external_id}:{sender}:{subject}"
    return hashlib.sha256(key.encode()).hexdigest()


def _parse_gmail_date(internal_date_ms: str | None) -> datetime:
    if internal_date_ms:
        ts = int(internal_date_ms) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def normalize_raw_event(raw_event_id: str) -> str | None:
    """Normalize a single raw_event into a message. Returns message_id or None if skipped."""
    with get_db() as db:
        event = db.query(RawEvent).filter_by(id=raw_event_id).first()
        if not event:
            log.error("raw_event_not_found", raw_event_id=raw_event_id)
            return None

        payload = event.payload_json
        sender = payload.get("sender", "")
        subject = payload.get("subject", "")
        body = payload.get("body_text", payload.get("snippet", ""))
        external_id = payload.get("gmail_id", event.external_id or "")

        dedup_hash = _compute_dedup_hash(event.user_id, external_id, sender, subject)

        # Parse Canvas
        canvas_result = parse_canvas_email(sender, subject, body)

        extra = {}
        if canvas_result.is_canvas:
            extra = {
                "canvas_type": canvas_result.canvas_type,
                "course_code": canvas_result.course_code,
                "assignment_title": canvas_result.assignment_title,
                "due_at_raw": canvas_result.due_at_raw,
                "canvas_url": canvas_result.canvas_url,
            }

        msg = Message(
            user_id=event.user_id,
            source_id=event.source_id,
            raw_event_id=event.id,
            external_id=external_id,
            sender=sender,
            title=subject or "(no subject)",
            body_preview=body[:500],
            body_full=body if len(body) > 500 else None,
            message_ts=_parse_gmail_date(payload.get("internal_date")),
            dedup_hash=dedup_hash,
            is_canvas=canvas_result.is_canvas,
            extra_json=extra,
        )

        try:
            db.add(msg)
            db.flush()
            msg_id = msg.id
            event.processed_at = datetime.now(tz=timezone.utc)
            db.commit()
            log.info("message_normalized", message_id=msg_id, raw_event_id=raw_event_id,
                     is_canvas=canvas_result.is_canvas)
            return msg_id
        except Exception as e:
            db.rollback()
            if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                # Already exists — mark raw event processed
                event.processed_at = datetime.now(tz=timezone.utc)
                db.commit()
                log.info("message_deduped", raw_event_id=raw_event_id)
                return None
            event.processing_error = str(e)
            db.commit()
            log.error("normalization_failed", raw_event_id=raw_event_id, error=str(e))
            return None


def normalize_all_pending() -> int:
    """Process all unprocessed raw_events. Returns count normalized."""
    with get_db() as db:
        pending_ids = [
            r.id for r in db.query(RawEvent.id)
            .filter(RawEvent.processed_at.is_(None))
            .filter(RawEvent.processing_error.is_(None))
        ]

    count = 0
    for raw_event_id in pending_ids:
        result = normalize_raw_event(str(raw_event_id))
        if result:
            count += 1
    return count
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: normalizer pipeline with dedup hashing and Canvas detection"
```

---

## Task 10: LLM Extractor with Retry

**Files to Create:**
- `packages/core/src/core/llm/__init__.py`
- `packages/core/src/core/llm/prompts/v1.py`
- `packages/core/src/core/llm/extractor.py`

**Step 1: Write prompts/v1.py**
```python
# packages/core/src/core/llm/prompts/v1.py
SYSTEM_PROMPT = """You are a precise data extraction assistant. Extract structured information from messages.
Output ONLY valid JSON matching the schema below. No extra keys. No markdown fences. No explanation.

Schema:
{
  "labels": [{"label": string, "confidence": 0.0-1.0}],
  "summary_short": string (max 100 chars),
  "summary_long": string (optional, max 500 chars),
  "action_items": [{
    "title": string,
    "details": string,
    "due_at": "ISO8601 datetime or null",
    "priority": 0-100,
    "confidence": 0.0-1.0
  }],
  "reply_drafts": [{"tone": "concise|neutral|formal", "draft_text": string}],
  "urgency": 0.0-1.0,
  "evidence": {"due_date_evidence": string or null, "source_url": string or null}
}

Valid labels: coursework, action_required, announcement, admin, social, deadline, interview, financial, other"""

USER_TEMPLATE = """User timezone: {timezone}
Source: {source_type}
Sender: {sender}
Subject: {title}
Timestamp: {message_ts}
Body:
{body}

Extract action items, due dates, and summaries."""
```

**Step 2: Write extractor.py**
```python
# packages/core/src/core/llm/extractor.py
import json
from datetime import datetime, timezone
from core.config import get_settings
from core.db.engine import get_db
from core.db.models import Message, MessageSummary, MessageLabel, ReplyDraft, ActionItem, Source
from core.schemas.llm import ExtractionResult
from core.llm.prompts.v1 import SYSTEM_PROMPT, USER_TEMPLATE
import structlog

log = structlog.get_logger()


def _call_llm(system: str, user: str) -> str:
    """Call Anthropic API and return raw text."""
    import anthropic
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _validate_extraction(raw_json: str) -> ExtractionResult:
    """Parse and validate JSON against strict schema."""
    data = json.loads(raw_json)
    return ExtractionResult.model_validate(data)


def extract_message(message_id: str, prompt_version: str = "v1") -> bool:
    """Run LLM extraction on a message. Returns True on success."""
    settings = get_settings()

    with get_db() as db:
        msg = db.query(Message).filter_by(id=message_id).first()
        if not msg:
            log.error("message_not_found", message_id=message_id)
            return False

        # Check if already extracted
        existing = db.query(MessageSummary).filter_by(
            message_id=message_id, prompt_version=prompt_version
        ).first()
        if existing:
            log.info("extraction_already_exists", message_id=message_id)
            return True

        source = db.query(Source).filter_by(id=msg.source_id).first()
        source_type = source.source_type if source else "unknown"

    if settings.llm_mode == "disabled":
        log.info("llm_disabled_skipping", message_id=message_id)
        return False

    body = _get_body(message_id)
    user_prompt = USER_TEMPLATE.format(
        timezone=settings.user_timezone,
        source_type=source_type,
        sender=msg.sender,
        title=msg.title,
        message_ts=msg.message_ts.isoformat(),
        body=body[:3000],
    )

    extraction = None
    failed = False

    try:
        raw = _call_llm(SYSTEM_PROMPT, user_prompt)
        extraction = _validate_extraction(raw)
    except Exception as e1:
        log.warning("extraction_first_attempt_failed", message_id=message_id, error=str(e1))
        try:
            repair_prompt = f"The previous output was invalid. Output ONLY valid JSON.\n\nOriginal message:\n{user_prompt}"
            raw = _call_llm(SYSTEM_PROMPT, repair_prompt)
            extraction = _validate_extraction(raw)
        except Exception as e2:
            log.error("extraction_failed_permanently", message_id=message_id, error=str(e2))
            failed = True

    with get_db() as db:
        summary = MessageSummary(
            message_id=message_id,
            prompt_version=prompt_version,
            summary_short=extraction.summary_short if extraction else "Extraction failed",
            summary_long=extraction.summary_long if extraction else None,
            urgency=extraction.urgency if extraction else 0.5,
            extraction_failed=failed,
        )
        db.add(summary)

        if extraction:
            for label in extraction.labels:
                db.add(MessageLabel(
                    message_id=message_id,
                    prompt_version=prompt_version,
                    label=label.label,
                    confidence=label.confidence,
                ))
            for draft in extraction.reply_drafts:
                db.add(ReplyDraft(
                    message_id=message_id,
                    prompt_version=prompt_version,
                    tone=draft.tone,
                    draft_text=draft.draft_text,
                ))
            for item in extraction.action_items:
                # Get user_id from message
                msg = db.query(Message).filter_by(id=message_id).first()
                db.add(ActionItem(
                    user_id=msg.user_id,
                    message_id=message_id,
                    title=item.title,
                    details=item.details,
                    due_at=item.due_at,
                    priority=item.priority,
                    confidence=item.confidence,
                    status="proposed",
                ))

        db.commit()
        log.info("extraction_saved", message_id=message_id, failed=failed,
                 action_items=len(extraction.action_items) if extraction else 0)

    return not failed


def _get_body(message_id: str) -> str:
    with get_db() as db:
        msg = db.query(Message).filter_by(id=message_id).first()
        return msg.body_full or msg.body_preview if msg else ""


def extract_all_pending(prompt_version: str = "v1") -> tuple[int, int]:
    """Extract all messages lacking a summary. Returns (success, failed)."""
    with get_db() as db:
        extracted_ids = {
            r.message_id for r in db.query(MessageSummary.message_id).all()
        }
        all_ids = [str(r.id) for r in db.query(Message.id).all()]
        pending = [mid for mid in all_ids if mid not in extracted_ids]

    success, failed = 0, 0
    for mid in pending:
        if extract_message(mid, prompt_version):
            success += 1
        else:
            failed += 1
    return success, failed
```

**Step 3: Commit**
```bash
git add .
git commit -m "feat: LLM extractor with Pydantic validation and retry on invalid JSON"
```

---

## Task 11: Task/Reminder Engine

**Files to Create:**
- `packages/core/src/core/pipeline/reminders.py`

**Step 1: Write reminders.py**
```python
# packages/core/src/core/pipeline/reminders.py
from datetime import datetime, timedelta, timezone
from core.db.engine import get_db
from core.db.models import ActionItem, Reminder, Policy
import structlog

log = structlog.get_logger()

CADENCES = {
    "gentle": [timedelta(hours=24), timedelta(hours=4)],
    "standard": [timedelta(hours=48), timedelta(hours=24), timedelta(hours=4)],
    "aggressive": [
        timedelta(hours=72), timedelta(hours=48),
        timedelta(hours=24), timedelta(hours=8), timedelta(hours=4)
    ],
}


def schedule_reminders_for_task(task_id: str, cadence: str = "standard") -> int:
    """Create reminder rows for a task. Returns count created."""
    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task or not task.due_at or task.status in ("done", "dismissed"):
            return 0

        offsets = CADENCES.get(cadence, CADENCES["standard"])
        count = 0
        for offset in offsets:
            remind_at = task.due_at - offset
            if remind_at <= datetime.now(tz=timezone.utc):
                continue
            reminder = Reminder(
                action_item_id=task_id,
                user_id=task.user_id,
                remind_at=remind_at,
                channel="cli",
                status="pending",
            )
            db.add(reminder)
            try:
                db.flush()
                count += 1
            except Exception:
                db.rollback()
                # Unique constraint — already scheduled
        db.commit()
        log.info("reminders_scheduled", task_id=task_id, count=count)
        return count


def get_policy_cadence(user_id: str) -> str:
    """Get today's reminder cadence from policy."""
    today = datetime.now(tz=timezone.utc).date()
    with get_db() as db:
        policy = db.query(Policy).filter_by(user_id=user_id, date=today).first()
        if policy:
            return policy.reminder_cadence
    return "standard"


def dispatch_due_reminders(now: datetime | None = None) -> int:
    """Mark pending reminders as sent if their time has passed. Returns count dispatched."""
    if now is None:
        now = datetime.now(tz=timezone.utc)
    with get_db() as db:
        due = db.query(Reminder).filter(
            Reminder.status == "pending",
            Reminder.remind_at <= now,
        ).all()
        count = 0
        for reminder in due:
            reminder.status = "sent"
            reminder.sent_at = now
            # Phase 1: just log
            log.info("reminder_dispatched", reminder_id=reminder.id,
                     action_item_id=reminder.action_item_id, channel=reminder.channel)
            count += 1
        db.commit()
    return count
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: reminder scheduling engine with policy-driven cadences"
```

---

## Task 12: PVI Engine

**Files to Create:**
- `packages/core/src/core/pvi/__init__.py`
- `packages/core/src/core/pvi/engine.py`

**Step 1: Write engine.py**
```python
# packages/core/src/core/pvi/engine.py
from datetime import datetime, timedelta, date, timezone
from core.db.engine import get_db
from core.db.models import (
    ActionItem, Message, PVIDailyFeature, PVIDailyScore, Policy
)
import structlog

log = structlog.get_logger()

REGIME_THRESHOLDS = {
    "overloaded": 75,
    "peak": 60,
    "normal": 40,
    "recovery": 0,
}


def compute_features(user_id: str, for_date: date) -> dict:
    now = datetime.combine(for_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_ago = now - timedelta(hours=24)

    with get_db() as db:
        tasks_open = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
        ).count()

        tasks_overdue = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status == "active",
            ActionItem.due_at < now,
        ).count()

        incoming_24h = db.query(Message).filter(
            Message.user_id == user_id,
            Message.ingested_at >= day_ago,
        ).count()

    return {
        "tasks_open": tasks_open,
        "tasks_overdue": tasks_overdue,
        "inbox_unread": 0,  # Populated from Gmail label unread count later
        "incoming_24h": incoming_24h,
        "calendar_minutes": 0,
    }


def score_from_features(features: dict) -> tuple[int, str]:
    """Returns (score 0-100, explanation)."""
    score = 50
    explanations = []

    # Overdue tasks are high weight
    overdue = features["tasks_overdue"]
    if overdue > 0:
        add = min(overdue * 10, 25)
        score += add
        explanations.append(f"tasks_overdue={overdue} (+{add})")

    # Open tasks
    open_tasks = features["tasks_open"]
    if open_tasks > 10:
        score += 10
        explanations.append(f"tasks_open={open_tasks} (+10)")
    elif open_tasks > 5:
        score += 5
        explanations.append(f"tasks_open={open_tasks} (+5)")

    # Inbox pressure
    unread = features["inbox_unread"]
    incoming = features["incoming_24h"]
    if unread > 50 or incoming > 30:
        score += 10
        explanations.append(f"inbox_pressure: unread={unread}, incoming={incoming} (+10)")
    elif unread > 20 or incoming > 15:
        score += 5
        explanations.append(f"inbox_pressure: unread={unread}, incoming={incoming} (+5)")

    # Relief: calm state
    if overdue == 0 and open_tasks <= 3 and incoming < 5:
        score -= 10
        explanations.append("calm_state (-10)")

    score = max(0, min(100, score))
    return score, "; ".join(explanations) if explanations else "baseline"


def classify_regime(score: int) -> str:
    if score >= REGIME_THRESHOLDS["overloaded"]:
        return "overloaded"
    elif score >= REGIME_THRESHOLDS["peak"]:
        return "peak"
    elif score >= REGIME_THRESHOLDS["normal"]:
        return "normal"
    else:
        return "recovery"


POLICY_MAP = {
    "overloaded": {"max_digest_items": 5, "escalation_level": "high",
                   "reminder_cadence": "aggressive", "auto_activate": False},
    "peak":       {"max_digest_items": 10, "escalation_level": "standard",
                   "reminder_cadence": "standard", "auto_activate": False},
    "normal":     {"max_digest_items": 15, "escalation_level": "standard",
                   "reminder_cadence": "standard", "auto_activate": False},
    "recovery":   {"max_digest_items": 20, "escalation_level": "low",
                   "reminder_cadence": "gentle", "auto_activate": False},
}


def compute_pvi_daily(user_id: str, for_date: date | None = None) -> dict:
    if for_date is None:
        for_date = datetime.now(tz=timezone.utc).date()

    features = compute_features(user_id, for_date)
    score, explanation = score_from_features(features)
    regime = classify_regime(score)
    policy = POLICY_MAP[regime]

    with get_db() as db:
        # Upsert features
        feat_row = db.query(PVIDailyFeature).filter_by(user_id=user_id, date=for_date).first()
        if feat_row:
            for k, v in features.items():
                setattr(feat_row, k, v)
            feat_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            feat_row = PVIDailyFeature(user_id=user_id, date=for_date, **features)
            db.add(feat_row)

        # Upsert score
        score_row = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()
        if score_row:
            score_row.score = score
            score_row.regime = regime
            score_row.explanation = explanation
            score_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            score_row = PVIDailyScore(
                user_id=user_id, date=for_date,
                score=score, regime=regime, explanation=explanation
            )
            db.add(score_row)

        # Upsert policy
        pol_row = db.query(Policy).filter_by(user_id=user_id, date=for_date).first()
        if pol_row:
            for k, v in policy.items():
                setattr(pol_row, k, v)
            pol_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            pol_row = Policy(user_id=user_id, date=for_date, regime=regime, **policy)
            db.add(pol_row)

        db.commit()
        log.info("pvi_computed", user_id=user_id, date=str(for_date),
                 score=score, regime=regime)

    return {"score": score, "regime": regime, "explanation": explanation,
            "features": features, "policy": policy}
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: rule-based PVI engine with regime classification and policy mapping"
```

---

## Task 13: Digest Generator

**Files to Create:**
- `packages/core/src/core/digest/__init__.py`
- `packages/core/src/core/digest/generator.py`

**Step 1: Write generator.py**
```python
# packages/core/src/core/digest/generator.py
from datetime import datetime, timedelta, date, timezone
from core.db.engine import get_db
from core.db.models import ActionItem, Message, MessageSummary, Policy, Digest, PVIDailyScore
import structlog

log = structlog.get_logger()


def generate_digest(user_id: str, for_date: date | None = None) -> str:
    if for_date is None:
        for_date = datetime.now(tz=timezone.utc).date()

    now = datetime.combine(for_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    day_end = now
    week_end = now + timedelta(days=7)

    with get_db() as db:
        # Get policy
        policy = db.query(Policy).filter_by(user_id=user_id, date=for_date).first()
        max_items = policy.max_digest_items if policy else 15
        regime = policy.regime if policy else "normal"
        cadence = policy.reminder_cadence if policy else "standard"

        # Get PVI
        pvi = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()

        # Do today: active/proposed tasks due within 24h
        do_today = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at <= day_end,
            ActionItem.due_at >= datetime.now(tz=timezone.utc),
        ).order_by(ActionItem.priority.desc()).limit(max_items).all()

        # Upcoming: due within 7 days
        upcoming = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at > day_end,
            ActionItem.due_at <= week_end,
        ).order_by(ActionItem.due_at, ActionItem.priority.desc()).limit(max_items).all()

        # Recent messages (announcements/updates)
        recent_messages = db.query(Message, MessageSummary).join(
            MessageSummary, MessageSummary.message_id == Message.id, isouter=True
        ).filter(
            Message.user_id == user_id,
            Message.ingested_at >= datetime.now(tz=timezone.utc) - timedelta(days=1),
        ).order_by(Message.message_ts.desc()).limit(max_items).all()

    lines = [f"# Clawdbot Digest — {for_date} (Policy: {regime}, max {max_items})", ""]

    lines.append("## DO TODAY")
    if do_today:
        for task in do_today:
            due_str = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "no due date"
            lines.append(f"- [ ] {task.title} (due {due_str}) [priority {task.priority}]")
            if task.details:
                lines.append(f"  {task.details}")
    else:
        lines.append("_Nothing due today_")

    lines += ["", "## UPCOMING"]
    if upcoming:
        for task in upcoming:
            due_str = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "no due date"
            lines.append(f"- [ ] {task.title} (due {due_str}) [priority {task.priority}; conf {task.confidence:.2f}]")
    else:
        lines.append("_Nothing in the next 7 days_")

    lines += ["", "## UPDATES"]
    if recent_messages:
        for msg, summary in recent_messages:
            short = summary.summary_short if summary else msg.body_preview[:80]
            canvas_tag = " [Canvas]" if msg.is_canvas else ""
            lines.append(f"- {msg.sender}{canvas_tag}: {short}")
    else:
        lines.append("_No recent updates_")

    if pvi:
        lines += ["", "## PVI"]
        lines.append(f"- Score: {pvi.score} ({pvi.regime})")
        lines.append(f"- Drivers: {pvi.explanation}")

    content = "\n".join(lines)

    with get_db() as db:
        existing = db.query(Digest).filter_by(user_id=user_id, date=for_date).first()
        if existing:
            existing.content_md = content
            existing.regime = regime
            existing.generated_at = datetime.now(tz=timezone.utc)
        else:
            db.add(Digest(user_id=user_id, date=for_date, content_md=content, regime=regime))
        db.commit()

    log.info("digest_generated", user_id=user_id, date=str(for_date))
    return content
```

**Step 2: Commit**
```bash
git add .
git commit -m "feat: digest generator with policy-capped sections"
```

---

## Task 14: FastAPI App + Endpoints

**Files to Create:**
- `apps/api/src/api/main.py`
- `apps/api/src/api/routes/inbox.py`
- `apps/api/src/api/routes/tasks.py`
- `apps/api/src/api/routes/digest.py`
- `apps/api/src/api/routes/pvi.py`
- `apps/api/src/api/routes/sync.py`
- `apps/api/src/api/routes/replay.py`

**Step 1: Write main.py**
```python
# apps/api/src/api/main.py
from fastapi import FastAPI
from api.routes import inbox, tasks, digest, pvi, sync, replay

app = FastAPI(title="Clawdbot Life Ops API", version="0.1.0")

app.include_router(sync.router, prefix="/v1/sync")
app.include_router(inbox.router, prefix="/v1/inbox")
app.include_router(tasks.router, prefix="/v1/tasks")
app.include_router(digest.router, prefix="/v1/digest")
app.include_router(pvi.router, prefix="/v1/pvi")
app.include_router(replay.router, prefix="/v1/replay")


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 2: Write sync.py route**
```python
# apps/api/src/api/routes/sync.py
from fastapi import APIRouter
from core.config import get_settings
from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending

router = APIRouter()


@router.post("/run")
def run_sync():
    settings = get_settings()
    normalized = normalize_all_pending()
    success, failed = extract_all_pending(settings.llm_prompt_version)
    return {"normalized": normalized, "extracted": success, "extraction_failed": failed}
```

**Step 3: Write tasks.py route**
```python
# apps/api/src/api/routes/tasks.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from core.db.engine import get_db
from core.db.models import ActionItem, Reminder

router = APIRouter()


@router.get("/")
def list_tasks(status: str | None = None, user_id: str = "00000000-0000-0000-0000-000000000001"):
    with get_db() as db:
        q = db.query(ActionItem).filter_by(user_id=user_id)
        if status:
            q = q.filter(ActionItem.status == status)
        tasks = q.order_by(ActionItem.due_at).all()
        return [{"id": t.id, "title": t.title, "status": t.status,
                 "due_at": t.due_at, "priority": t.priority} for t in tasks]


def _update_task_status(task_id: str, new_status: str):
    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        task.status = new_status
        task.updated_at = datetime.now(tz=timezone.utc)
        if new_status in ("done", "dismissed"):
            db.query(Reminder).filter_by(action_item_id=task_id, status="pending").update(
                {"status": "cancelled"}
            )
        db.commit()
        return {"id": task_id, "status": new_status}


@router.post("/{task_id}/accept")
def accept_task(task_id: str):
    return _update_task_status(task_id, "active")


@router.post("/{task_id}/done")
def done_task(task_id: str):
    return _update_task_status(task_id, "done")


@router.post("/{task_id}/dismiss")
def dismiss_task(task_id: str):
    return _update_task_status(task_id, "dismissed")


class SnoozeRequest(BaseModel):
    hours: int


@router.post("/{task_id}/snooze")
def snooze_task(task_id: str, req: SnoozeRequest):
    with get_db() as db:
        reminder = db.query(Reminder).filter_by(
            action_item_id=task_id, status="pending"
        ).order_by(Reminder.remind_at).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="No pending reminders")
        reminder.remind_at = reminder.remind_at + timedelta(hours=req.hours)
        reminder.status = "snoozed"
        db.commit()
        return {"snoozed_until": reminder.remind_at}
```

**Step 4: Write remaining routes (inbox, digest, pvi, replay) — see full code in repo**

The inbox route queries messages+summaries, digest route calls generate_digest, pvi route calls compute_pvi_daily, replay route re-runs extraction with a new prompt_version.

**Step 5: Commit**
```bash
git add .
git commit -m "feat: FastAPI app with all Phase 1 endpoints"
```

---

## Task 15: Worker/Scheduler (APScheduler)

**Files to Create:**
- `apps/worker/src/worker/main.py`
- `apps/worker/src/worker/jobs.py`

**Step 1: Write jobs.py**
```python
# apps/worker/src/worker/jobs.py
from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending
from core.pipeline.reminders import dispatch_due_reminders, schedule_reminders_for_task, get_policy_cadence
from core.pvi.engine import compute_pvi_daily
from core.digest.generator import generate_digest
from core.db.engine import get_db
from core.db.models import ActionItem, User
from core.config import get_settings
import structlog

log = structlog.get_logger()


def job_poll_and_normalize():
    """Poll Gmail and normalize new raw events."""
    from connectors.gmail.poller import poll_gmail
    settings = get_settings()
    with get_db() as db:
        from core.db.models import Source
        sources = db.query(Source).filter_by(source_type="gmail").all()
        for source in sources:
            poll_gmail(str(source.user_id), str(source.id))
    normalize_all_pending()


def job_extract_pending():
    settings = get_settings()
    success, failed = extract_all_pending(settings.llm_prompt_version)
    log.info("extraction_job_done", success=success, failed=failed)


def job_schedule_reminders():
    with get_db() as db:
        tasks = db.query(ActionItem).filter(
            ActionItem.status.in_(["active", "proposed"]),
            ActionItem.due_at.isnot(None),
        ).all()
        for task in tasks:
            cadence = get_policy_cadence(str(task.user_id))
            schedule_reminders_for_task(str(task.id), cadence)
    dispatch_due_reminders()


def job_daily_pvi_and_digest():
    with get_db() as db:
        users = db.query(User).all()
        for user in users:
            compute_pvi_daily(str(user.id))
            generate_digest(str(user.id))
```

**Step 2: Write main.py**
```python
# apps/worker/src/worker/main.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from worker.jobs import (
    job_poll_and_normalize, job_extract_pending,
    job_schedule_reminders, job_daily_pvi_and_digest
)
from core.config import get_settings
import structlog

log = structlog.get_logger()


def start():
    settings = get_settings()
    scheduler = BlockingScheduler()

    scheduler.add_job(
        job_poll_and_normalize,
        IntervalTrigger(minutes=settings.gmail_poll_interval_minutes),
        id="poll_gmail",
    )
    scheduler.add_job(
        job_extract_pending,
        IntervalTrigger(minutes=5),
        id="extract_pending",
    )
    scheduler.add_job(
        job_schedule_reminders,
        IntervalTrigger(minutes=1),
        id="dispatch_reminders",
    )
    scheduler.add_job(
        job_daily_pvi_and_digest,
        CronTrigger(hour=7, minute=0),
        id="daily_pvi_digest",
    )

    log.info("scheduler_starting")
    scheduler.start()


if __name__ == "__main__":
    start()
```

**Step 3: Commit**
```bash
git add .
git commit -m "feat: APScheduler worker with poll/extract/remind/digest jobs"
```

---

## Task 16: CLI (claw commands)

**Files to Create:**
- `packages/cli/src/cli/main.py`
- `packages/cli/src/cli/commands/init.py`
- `packages/cli/src/cli/commands/connect.py`
- `packages/cli/src/cli/commands/sync.py`
- `packages/cli/src/cli/commands/inbox.py`
- `packages/cli/src/cli/commands/tasks.py`
- `packages/cli/src/cli/commands/digest.py`
- `packages/cli/src/cli/commands/pvi.py`
- `packages/cli/src/cli/commands/replay.py`

**Step 1: Write main.py**
```python
# packages/cli/src/cli/main.py
import typer
from cli.commands import init, connect, sync, inbox, tasks, digest, pvi, replay

app = typer.Typer(name="claw", help="Clawdbot Life Ops CLI")
app.add_typer(connect.app, name="connect")
app.add_typer(inbox.app, name="inbox")
app.add_typer(tasks.app, name="tasks")
app.add_typer(replay.app, name="replay")

app.command("init")(init.cmd_init)
app.command("sync")(sync.cmd_sync)
app.command("digest")(digest.cmd_digest)
app.command("pvi")(pvi.cmd_pvi)
app.command("snooze")(tasks.cmd_snooze)

if __name__ == "__main__":
    app()
```

**Step 2: Write init command**
```python
# packages/cli/src/cli/commands/init.py
import typer
from rich import print as rprint
from core.db.engine import get_engine
from core.db.models import Base, User
from core.config import get_settings
from core.db.engine import get_db


def cmd_init():
    """Initialize the Clawdbot database and default user."""
    settings = get_settings()
    rprint("[bold]Clawdbot Life Ops — Init[/bold]")

    with get_db() as db:
        existing = db.query(User).filter_by(id=settings.default_user_id).first()
        if not existing:
            user = User(
                id=settings.default_user_id,
                email="local@clawdbot",
                display_name="Local User",
                timezone=settings.user_timezone,
            )
            db.add(user)
            db.commit()
            rprint(f"[green]✓ Created default user[/green]")
        else:
            rprint(f"[yellow]User already exists[/yellow]")

    rprint("[green]✓ Init complete. Run: claw connect gmail[/green]")
```

**Step 3: Write connect command**
```python
# packages/cli/src/cli/commands/connect.py
import typer
from rich import print as rprint
from pathlib import Path

app = typer.Typer()


@app.command("gmail")
def connect_gmail(
    credentials: str = typer.Option(
        "~/.config/clawdbot/gmail_credentials.json",
        "--credentials", "-c",
        help="Path to Google OAuth credentials JSON"
    )
):
    """Connect Gmail via OAuth."""
    from connectors.gmail.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()
    creds_path = str(Path(credentials).expanduser())

    if not Path(creds_path).exists():
        rprint(f"[red]Credentials file not found: {creds_path}[/red]")
        rprint("Download OAuth credentials from Google Cloud Console.")
        raise typer.Exit(1)

    rprint("Opening browser for Gmail OAuth...")
    run_oauth_flow(creds_path)
    rprint("[green]✓ Gmail connected[/green]")

    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gmail"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="gmail",
                display_name="Gmail",
                config_json={},
            ))
            db.commit()
            rprint("[green]✓ Gmail source registered[/green]")
```

**Step 4: Write sync, inbox, tasks, digest, pvi, replay commands (condensed)**
Each command calls the relevant pipeline functions and renders output with Rich tables.

- `claw sync` → calls `normalize_all_pending()` + `extract_all_pending()`
- `claw inbox` → queries messages with summaries, renders Rich table
- `claw tasks [--status]` → queries action_items
- `claw tasks accept|done|dismiss <id>` → updates status
- `claw digest today` → calls `generate_digest()`, prints markdown
- `claw pvi today` → calls `compute_pvi_daily()`, prints score/regime
- `claw replay extract` → re-runs extraction with new prompt version

**Step 5: Commit**
```bash
git add .
git commit -m "feat: complete claw CLI with all Phase 1 commands"
```

---

## Task 17: Unit Tests

**Files to Create:**
- `tests/unit/test_dedup.py`
- `tests/unit/test_canvas_parser.py`
- `tests/unit/test_pvi.py`
- `tests/unit/test_llm_schema.py`
- `tests/unit/test_reminders.py`

**Step 1: Write test_dedup.py**
```python
# tests/unit/test_dedup.py
import hashlib
from core.pipeline.normalizer import _compute_dedup_hash


def test_dedup_hash_is_stable():
    h1 = _compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = _compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    assert h1 == h2


def test_dedup_hash_differs_for_different_external_id():
    h1 = _compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = _compute_dedup_hash("user1", "gmail456", "test@example.com", "Hello")
    assert h1 != h2


def test_dedup_hash_differs_for_different_user():
    h1 = _compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = _compute_dedup_hash("user2", "gmail123", "test@example.com", "Hello")
    assert h1 != h2
```

**Step 2: Write test_canvas_parser.py (≥5 fixtures)**
```python
# tests/unit/test_canvas_parser.py
import pytest
from connectors.canvas.parser import parse_canvas_email, is_canvas_email

FIXTURES = [
    {
        "name": "assignment_due",
        "sender": "notifications@instructure.com",
        "subject": "Assignment due: CS3230 Problem Set 4",
        "body": "Your assignment CS3230 Problem Set 4 is due Mar 9 23:59. Submit at https://canvas.nus.edu.sg/courses/123/assignments/456",
        "expect_canvas": True,
        "expect_type": "assignment",
        "expect_course": "CS3230",
        "expect_url_contains": "assignments",
    },
    {
        "name": "announcement",
        "sender": "no-reply@canvas.example.edu",
        "subject": "CS2100 Announcement: Lecture venue change",
        "body": "Announcement from CS2100: The lecture venue has changed to SR1.",
        "expect_canvas": True,
        "expect_type": "announcement",
        "expect_course": "CS2100",
        "expect_url_contains": None,
    },
    {
        "name": "grade_posted",
        "sender": "no-reply@instructure.com",
        "subject": "Grade posted for CS3230",
        "body": "Your grade has been posted for CS3230 Assignment 3. You scored 85/100.",
        "expect_canvas": True,
        "expect_type": "grade",
        "expect_course": "CS3230",
        "expect_url_contains": None,
    },
    {
        "name": "quiz_reminder",
        "sender": "notifications@instructure.com",
        "subject": "Quiz due soon: CS2040 Quiz 3",
        "body": "CS2040 Quiz 3 is due tomorrow at 09:00. Complete at https://canvas.example.edu/courses/99/quizzes/77",
        "expect_canvas": True,
        "expect_type": "quiz",
        "expect_course": "CS2040",
        "expect_url_contains": "quizzes",
    },
    {
        "name": "non_canvas_email",
        "sender": "boss@company.com",
        "subject": "Meeting tomorrow",
        "body": "Let's meet at 3pm.",
        "expect_canvas": False,
        "expect_type": None,
        "expect_course": None,
        "expect_url_contains": None,
    },
    {
        "name": "canvas_with_iso_due_date",
        "sender": "noreply@instructure.com",
        "subject": "Submission: CS4248 Project Report",
        "body": "Due: 2026-03-15T23:59:00. Submit at https://canvas.school.edu/courses/10/assignments/20",
        "expect_canvas": True,
        "expect_type": "assignment",
        "expect_course": "CS4248",
        "expect_url_contains": "assignments",
    },
]


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_canvas_parser(fixture):
    result = parse_canvas_email(fixture["sender"], fixture["subject"], fixture["body"])
    assert result.is_canvas == fixture["expect_canvas"]
    if fixture["expect_canvas"]:
        assert result.canvas_type == fixture["expect_type"]
        if fixture["expect_course"]:
            assert result.course_code == fixture["expect_course"]
        if fixture["expect_url_contains"]:
            assert fixture["expect_url_contains"] in (result.canvas_url or "")
```

**Step 3: Write test_pvi.py**
```python
# tests/unit/test_pvi.py
from core.pvi.engine import score_from_features, classify_regime, POLICY_MAP


def test_baseline_score_is_50():
    score, _ = score_from_features({
        "tasks_open": 0, "tasks_overdue": 0,
        "inbox_unread": 0, "incoming_24h": 0, "calendar_minutes": 0
    })
    # Calm state bonus applies: 50 - 10 = 40
    assert score == 40


def test_overdue_tasks_increase_score():
    score, explanation = score_from_features({
        "tasks_open": 5, "tasks_overdue": 3,
        "inbox_unread": 0, "incoming_24h": 0, "calendar_minutes": 0
    })
    assert score > 50
    assert "tasks_overdue" in explanation


def test_overloaded_regime():
    assert classify_regime(80) == "overloaded"


def test_peak_regime():
    assert classify_regime(65) == "peak"


def test_normal_regime():
    assert classify_regime(50) == "normal"


def test_recovery_regime():
    assert classify_regime(20) == "recovery"


def test_policy_map_completeness():
    for regime in ["overloaded", "peak", "normal", "recovery"]:
        policy = POLICY_MAP[regime]
        assert "max_digest_items" in policy
        assert "reminder_cadence" in policy
        assert "auto_activate" in policy
```

**Step 4: Write test_llm_schema.py**
```python
# tests/unit/test_llm_schema.py
import pytest
from pydantic import ValidationError
from core.schemas.llm import ExtractionResult

VALID_EXTRACTION = {
    "labels": [{"label": "coursework", "confidence": 0.9}],
    "summary_short": "Assignment due Monday",
    "summary_long": "Detailed summary here.",
    "action_items": [{
        "title": "Submit assignment",
        "details": "Upload PDF",
        "due_at": "2026-03-09T23:59:00+08:00",
        "priority": 85,
        "confidence": 0.8
    }],
    "reply_drafts": [],
    "urgency": 0.7,
}


def test_valid_extraction_parses():
    result = ExtractionResult.model_validate(VALID_EXTRACTION)
    assert len(result.action_items) == 1
    assert result.urgency == 0.7


def test_extra_key_raises():
    bad = {**VALID_EXTRACTION, "unexpected_field": "bad"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_confidence_out_of_range_raises():
    bad = {**VALID_EXTRACTION, "urgency": 1.5}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_missing_required_field_raises():
    bad = {k: v for k, v in VALID_EXTRACTION.items() if k != "summary_short"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)
```

**Step 5: Write test_reminders.py**
```python
# tests/unit/test_reminders.py
from datetime import datetime, timedelta, timezone
from core.pipeline.reminders import CADENCES, schedule_reminders_for_task


def test_cadences_exist():
    for name in ["gentle", "standard", "aggressive"]:
        assert name in CADENCES
        assert len(CADENCES[name]) >= 1


def test_standard_cadence_has_three_offsets():
    assert len(CADENCES["standard"]) == 3


def test_reminder_offsets_are_timedeltas():
    for cadence in CADENCES.values():
        for offset in cadence:
            assert isinstance(offset, timedelta)
```

**Step 6: Run tests**
```bash
cd /path/to/project
python -m pytest tests/unit/ -v
```
Expected: all tests pass.

**Step 7: Commit**
```bash
git add .
git commit -m "test: unit tests for dedup, canvas parser, pvi, llm schema, reminders"
```

---

## Task 18: Integration Tests + Structured Logging

**Files to Create:**
- `tests/integration/test_pipeline.py`
- `packages/core/src/core/logging.py`

**Step 1: Write logging.py**
```python
# packages/core/src/core/logging.py
import structlog
import logging


def configure_logging(level: str = "INFO"):
    logging.basicConfig(level=getattr(logging, level))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

**Step 2: Write integration test**
```python
# tests/integration/test_pipeline.py
"""End-to-end pipeline test using fixture raw events and a fake LLM."""
import pytest
from unittest.mock import patch
import json

FAKE_EXTRACTION = json.dumps({
    "labels": [{"label": "coursework", "confidence": 0.9}],
    "summary_short": "Test assignment due",
    "action_items": [{
        "title": "Submit test assignment",
        "details": "Upload to Canvas",
        "due_at": None,
        "priority": 70,
        "confidence": 0.8
    }],
    "reply_drafts": [],
    "urgency": 0.6,
})


@pytest.fixture
def db_with_user(tmp_path):
    """Set up test DB with user and source."""
    # Uses in-memory SQLite for integration tests
    # (override DATABASE_URL env var in conftest)
    pass  # Implement with pytest fixtures and test DB


def test_pipeline_end_to_end():
    """Fixture raw event → normalize → extract → task created."""
    # This test requires a test database setup
    # Implement with real DB or use conftest to set up test DB
    pass
```

**Step 3: Add Dockerfiles**
```dockerfile
# apps/api/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e packages/core -e packages/connectors -e apps/api
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 4: Write README with setup commands**
```markdown
# Clawdbot Life Ops

## Quick Start

1. Start Postgres:
   ```bash
   docker-compose -f infra/docker-compose.yml up -d db
   ```

2. Run migrations:
   ```bash
   cd infra && alembic upgrade head
   ```

3. Install CLI:
   ```bash
   pip install -e packages/core -e packages/connectors -e packages/cli
   ```

4. Initialize:
   ```bash
   claw init
   claw connect gmail
   claw sync
   claw digest today
   ```
```

**Step 5: Final commit**
```bash
git add .
git commit -m "feat: integration tests, structured logging, Dockerfiles, README"
```

---

## CONTEXT CHECKPOINT

If context exceeds 70%, save progress here and resume from the next unchecked task.

**Current implementation status:** [update as tasks complete]
**Next task to implement:** [update when resuming]
**Key decisions made:**
- Background jobs: APScheduler + Postgres (no Redis)
- Canvas ingestion: email-bridge parser (Phase 1), NUS-tuned
- Token storage: keyring with file fallback
- LLM: Anthropic claude-sonnet-4-6 via `anthropic` SDK
- Dedup: SHA-256 of user_id + external_id + sender + subject
- Telegram: Phase 1 delivery (digest at 7am + reminder push)
- LLM scope: configurable label filter (default: INBOX + UNREAD)
- DB: Postgres-only via Docker; test DB = clawdbot_test

---

## ADDENDA — Improvements from Brainstorming

### A1: NUS Canvas Parser Improvements (Task 8)

Add to `CANVAS_SENDER_PATTERNS`:
```python
r"canvas\.nus\.edu\.sg",
r".*@nus\.edu\.sg",
```

Add to `COURSE_CODE_PATTERNS` (NUS codes: CS3230, MA1101R, GEA1000N, IS4010S):
```python
r"\b([A-Z]{2,3}\d{4}[A-Z]?)\b",  # NUS format - more specific than generic
```

Add NUS-specific fixture to `test_canvas_parser.py`:
```python
{
    "name": "nus_canvas_assignment",
    "sender": "notifications@instructure.com",
    "subject": "New Assignment for CS3230: Problem Set 3",
    "body": "Due: Mar 9, 2026 11:59pm\nhttps://canvas.nus.edu.sg/courses/123/assignments/456",
    "expect_canvas": True,
    "expect_course": "CS3230",
    "expect_url_contains": "canvas.nus.edu.sg",
}
```

---

### A2: Gmail Backoff Strategy (Task 7)

Add to `poller.py` before API calls:
```python
import time
from googleapiclient.errors import HttpError

def _with_backoff(fn, max_retries=3):
    """Exponential backoff for Gmail API quota errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status in (429, 403) and attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("gmail_quota_backoff", attempt=attempt, wait_seconds=wait)
                time.sleep(wait)
            else:
                raise
```

Wrap all `service.users().*().execute()` calls with `_with_backoff(lambda: ...)`.

---

### A3: LLM Label Filter Config (Tasks 2 + 10)

Add to `Settings` in `core/config.py`:
```python
llm_label_filter: list[str] = Field(default=["INBOX", "UNREAD"])
# Messages must have ALL of these labels to trigger LLM extraction
llm_filter_canvas_always: bool = Field(default=True)
# Canvas emails always get extracted regardless of label filter
```

Add to `extractor.py` before calling `_call_llm`:
```python
# Check label filter
msg_labels = payload.get("label_ids", [])
settings = get_settings()
passes_filter = (
    msg.is_canvas and settings.llm_filter_canvas_always
) or all(lbl in msg_labels for lbl in settings.llm_label_filter)

if not passes_filter:
    log.info("extraction_skipped_label_filter", message_id=message_id)
    return True  # Not a failure, just skipped
```

---

### A4: llm_runs Audit Table (Task 3 migration + Task 4 models)

Add to migration `0001_initial_schema.py`:
```sql
CREATE TABLE llm_runs (
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
CREATE INDEX idx_llm_runs_message ON llm_runs(message_id, prompt_version);
```

Add `LLMRun` ORM model and log a row in `extractor.py` after each API call:
```python
import time
start = time.monotonic()
raw = _call_llm(SYSTEM_PROMPT, user_prompt)
latency_ms = int((time.monotonic() - start) * 1000)
# ... validate ...
db.add(LLMRun(
    message_id=message_id,
    prompt_version=prompt_version,
    model=settings.llm_model,
    latency_ms=latency_ms,
    validation_passed=not failed,
    attempt=attempt_number,
))
```

---

### A5: Telegram Bot Setup + Delivery (Task 16 — new)

**Step 1: Create bot via BotFather**
1. Open Telegram, search `@BotFather`
2. Send `/newbot`, follow prompts to name your bot
3. Copy the API token (format: `123456789:ABCdef...`)
4. Send a message to your bot, then fetch your chat_id:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   # Look for "chat": {"id": YOUR_CHAT_ID}
   ```
5. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   TELEGRAM_CHAT_ID=987654321
   ```

**Step 2: Add to Settings**
```python
telegram_bot_token: str = Field(default="")
telegram_chat_id: str = Field(default="")
telegram_enabled: bool = Field(default=False)
```

**Step 3: Write `packages/core/src/core/telegram_client.py`**
```python
import httpx
import structlog

log = structlog.get_logger()


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            resp.raise_for_status()
            log.info("telegram_sent", chat_id=chat_id)
            return True
    except Exception as e:
        log.error("telegram_failed", error=str(e))
        return False
```

**Step 4: Wire into worker jobs**
In `apps/worker/src/worker/jobs.py`, after `generate_digest()`:
```python
import asyncio
from core.telegram_client import send_telegram_message

async def _push_digest_to_telegram(user_id: str):
    settings = get_settings()
    if not settings.telegram_enabled:
        return
    with get_db() as db:
        from core.db.models import Digest
        from datetime import date
        digest = db.query(Digest).filter_by(user_id=user_id, date=date.today()).first()
        if digest:
            await send_telegram_message(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                digest.content_md[:4096],  # Telegram message limit
            )

def job_daily_pvi_and_digest():
    # ... existing code ...
    asyncio.run(_push_digest_to_telegram(str(user.id)))
```

Also update `dispatch_due_reminders()` in `reminders.py` to push via Telegram:
```python
if settings.telegram_enabled:
    asyncio.run(send_telegram_message(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        f"⏰ Reminder: *{task.title}*\nDue: {task.due_at.strftime('%Y-%m-%d %H:%M')}",
    ))
```

Add `python-telegram-bot` removed in favor of direct `httpx` calls (simpler, no extra dependency).

---

### A6: Test conftest.py + test DB setup (Task 18)

Create `tests/conftest.py`:
```python
import pytest
import os
from sqlalchemy import create_engine, text
from core.db.engine import get_engine
from core.db.models import Base

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://clawdbot:clawdbot@localhost:5432/clawdbot_test"
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create test database schema before tests, drop after."""
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def override_db_url(monkeypatch):
    """Point all DB calls to test DB during tests."""
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    # Reset cached engine
    import core.db.engine as eng
    eng._engine = None
    yield
    eng._engine = None
```

Create test DB:
```bash
docker exec -it <postgres_container> psql -U clawdbot -c "CREATE DATABASE clawdbot_test;"
```

---

### A7: Missing CLI commands (Task 17 — fully coded)

**`claw inbox` with Rich table:**
```python
@app.command("inbox")
def cmd_inbox(limit: int = typer.Option(50, "--limit", "-n")):
    from rich.table import Table
    from rich.console import Console
    console = Console()
    with get_db() as db:
        rows = (db.query(Message, MessageSummary)
                .join(MessageSummary, MessageSummary.message_id == Message.id, isouter=True)
                .filter(Message.user_id == settings.default_user_id)
                .order_by(Message.message_ts.desc())
                .limit(limit).all())
    table = Table(title="Inbox", show_lines=False)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Source", width=8)
    table.add_column("From", width=25)
    table.add_column("Subject", width=40)
    table.add_column("Time", width=12)
    table.add_column("Summary", width=40)
    for msg, summary in rows:
        short_id = msg.id[:8]
        source = "[cyan]Canvas[/cyan]" if msg.is_canvas else "Gmail"
        short = summary.summary_short if summary else ""
        table.add_row(short_id, source, msg.sender[:24], msg.title[:39],
                      msg.message_ts.strftime("%m-%d %H:%M"), short[:39])
    console.print(table)
```

**`claw inbox search <query>`:**
```python
@app.command("search")
def cmd_search(query: str):
    with get_db() as db:
        rows = db.query(Message).filter(
            Message.user_id == settings.default_user_id,
            or_(Message.title.ilike(f"%{query}%"),
                Message.sender.ilike(f"%{query}%"),
                Message.body_preview.ilike(f"%{query}%"))
        ).order_by(Message.message_ts.desc()).limit(20).all()
    # render with Rich table (same pattern as inbox)
```

**`claw pvi today`:**
```python
def cmd_pvi():
    from core.pvi.engine import compute_pvi_daily
    settings = get_settings()
    result = compute_pvi_daily(settings.default_user_id)
    rprint(f"[bold]PVI Score:[/bold] {result['score']} ({result['regime'].upper()})")
    rprint(f"[bold]Drivers:[/bold] {result['explanation']}")
    rprint(f"[bold]Policy:[/bold] max_digest={result['policy']['max_digest_items']}, "
           f"cadence={result['policy']['reminder_cadence']}")
```

---

### A8: `claw reminders due` command (Task 17)

```python
@app.command("reminders")
def cmd_reminders():
    """Show reminders due in the next 24 hours."""
    from datetime import datetime, timedelta, timezone
    from core.db.models import Reminder, ActionItem
    cutoff = datetime.now(tz=timezone.utc) + timedelta(hours=24)
    with get_db() as db:
        due = (db.query(Reminder, ActionItem)
               .join(ActionItem, ActionItem.id == Reminder.action_item_id)
               .filter(Reminder.status == "pending", Reminder.remind_at <= cutoff)
               .order_by(Reminder.remind_at).all())
    for reminder, task in due:
        rprint(f"[yellow]⏰[/yellow] {reminder.remind_at.strftime('%m-%d %H:%M')} — {task.title}")
```
