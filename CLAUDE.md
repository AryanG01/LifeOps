# Clawdbot — Claude Code Rules

## Context Management (MANDATORY)
- **At 70% context usage: STOP current task, update the active plan file, update MEMORY.md, then tell the user to run `/clear` and resume.**
- Active plan file: `docs/plans/2026-03-04-clawdbot-phase4.md`
- Always resume from the plan file — it is the source of truth for task progress.

## Project
Personal ops bot — Gmail + Outlook/NUS → LLM extraction → tasks/reminders/PVI/digest → Telegram.

## Key Rules
- Run all `claw` commands from the **project root** (`/Users/aryanganju/Desktop/Code/LifeOps`), NOT from `infra/`
- Run migrations from `infra/`: `cd infra && python3 -m alembic upgrade head`
- Tests: `python3 -m pytest tests/unit/ -v` from project root
- ORM objects MUST be accessed inside `with get_db() as db:` block (DetachedInstanceError otherwise)
- All new CLI command imports go inside the function body (lazy imports — avoid circular deps)

## Active Plan
`docs/plans/2026-03-04-clawdbot-phase4.md` — 10 tasks, Phase 4
