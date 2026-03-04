# Clawdbot — What It Does

Clawdbot is a personal assistant that reads your emails, figures out what needs action, and keeps you on top of things via Telegram and a CLI.

---

## Where It Gets Data

| Source | What it reads |
|--------|--------------|
| Gmail | All emails matching your label filter (default: INBOX + UNREAD) |
| Outlook / NUS Exchange | Emails via Microsoft Graph API |
| Google Calendar | Events for the next 14 days |
| Canvas (NUS) | Assignment deadlines and announcements embedded in emails |

---

## The Pipeline (how data flows)

```
Email arrives
    ↓
Raw event stored (never deleted — everything is replayable)
    ↓
LLM triage: is this worth processing? (cheap, fast pre-check)
    ↓
Normalizer: extract sender, subject, body, timestamp
    ↓
Canvas check: is this a Canvas notification? Extract deadline.
    ↓
LLM extraction: pull out action items, urgency, reminders
    ↓
Tasks + Reminders created in DB
    ↓
Telegram push / CLI display
```

---

## Features

### Email Sync

- **Gmail**: Uses the History API — only fetches what's new since last sync (fast, ~2 min latency)
- **Outlook**: Polls Microsoft Graph delta endpoint every 2 minutes
- **Deduplication**: Same email never processed twice (SHA-256 hash per message)
- **Canvas parser**: Detects NUS Canvas emails and pulls out course code, assignment title, due date, and URL

### LLM Extraction

- **Two providers**: Gemini (default, free) or Anthropic Claude — switch with `claw llm use gemini/anthropic`
- **Triage gate**: A cheap, fast model checks if an email is worth full extraction before spending tokens
- **Extracts**: Summary, action items, urgency score (0-10), labels, reminder times
- **Audit log**: Every LLM call is recorded in the `llm_runs` table

### Tasks

- Create action items from emails automatically
- Mark tasks done, snooze them, set due dates
- View your task list from CLI

### Reminders

- Automatically scheduled from extracted action items
- Three cadences: standard (3 nudges), gentle (2 nudges), aggressive (5 nudges)
- Pushed to Telegram at the right time
- Silenced during focus sessions (see Focus mode)

### PVI (Personal Velocity Index)

A daily score (0–100) that reflects how busy / overloaded you are:

| Score | Regime | What it means |
|-------|--------|---------------|
| 75–100 | Overloaded | Too much on your plate |
| 60–74 | Peak | At capacity, high output |
| 40–59 | Normal | Comfortable pace |
| 0–39 | Recovery | Light load |

The score feeds into how many digest items you see and which reminder cadence is used.

### Daily Digest

Sent to Telegram at 7am every day. Includes:
- Unread emails summary
- Open tasks and overdue items
- Upcoming calendar events
- Your current PVI score and regime

Run manually: `claw digest`

### Weekly Review

A summary of the past 7 days:
- PVI trend sparkline (7 bars showing each day)
- Task completion rate
- Overdue items still outstanding
- Total emails processed

Run manually: `claw digest --weekly`

### Morning Briefing (`claw today`)

A quick morning summary you can run from the terminal:
- Today's calendar events
- Open tasks due today or overdue
- Current PVI and what it means for you

### Focus / DND Mode

Temporarily silences Telegram reminders so you can work without interruptions.

```
claw focus start 90m    # focus for 90 minutes
claw focus status       # check if focus is active
claw focus end          # end early
```

Reminders are queued and resume after focus ends.

### Google Calendar

- Polls your calendar every 15 minutes for events in the next 14 days
- Meeting prep: 30 minutes before a meeting, generates a 3-bullet prep summary using recent emails from attendees — pushed to Telegram

### Reply Drafting

When an email likely needs a reply, Clawdbot drafts one using the LLM.

```
claw reply list         # see emails with draft replies
claw reply view <id>    # read the draft
claw reply send <id>    # send it via Gmail
```

### TUI Dashboard (`claw dash`)

A terminal dashboard (press `q` to quit) showing:
- Recent inbox messages
- Open tasks
- Active reminders
- Today's calendar events
- Current PVI

### Background Worker

Runs all polling and processing jobs automatically:

| Job | Frequency |
|-----|-----------|
| Poll Gmail | Every 2 min |
| Poll Outlook | Every 2 min |
| Poll Google Calendar | Every 15 min |
| Run LLM extraction | Every 5 min |
| Dispatch reminders | Every 1 min |
| Meeting prep | Every 5 min |
| Daily digest + PVI | 7am daily |

Start with: `claw worker start`

---

## CLI Reference

```
claw init                        # set up user in DB
claw status                      # system health (DB, Gmail, LLM, Telegram)
claw sync                        # manually poll all sources

claw connect gmail               # link Gmail account
claw connect outlook             # link Outlook / NUS Exchange
claw connect gcal                # link Google Calendar

claw today                       # morning briefing
claw dash                        # terminal dashboard

claw inbox list                  # view recent emails
claw tasks list                  # view open tasks
claw tasks done <id>             # mark task complete
claw snooze <id> 2h              # snooze a task

claw reminders list              # view upcoming reminders

claw focus start <duration>      # start focus session (e.g. 30m, 1h)
claw focus status                # check focus status
claw focus end                   # end focus early

claw reply list                  # view draft replies
claw reply view <id>             # read a draft
claw reply send <id>             # send via Gmail

claw digest                      # daily digest
claw digest --weekly             # weekly review

claw pvi                         # view today's PVI score

claw llm status                  # show active LLM provider
claw llm use gemini              # switch to Gemini
claw llm use anthropic           # switch to Anthropic
claw llm test                    # send a test prompt

claw telegram setup              # configure Telegram bot token + chat ID
claw telegram test               # send a test message

claw worker start                # start background scheduler
```

---

## Data Storage

All data lives in PostgreSQL. Key tables:

| Table | Stores |
|-------|--------|
| `users` | Your user account |
| `sources` | Connected accounts (Gmail, Outlook, GCal) |
| `raw_events` | Every raw email/event ever received (immutable) |
| `messages` | Normalised emails with dedup |
| `action_items` | Tasks extracted by LLM |
| `reminders` | Scheduled nudges |
| `pvi_daily_scores` | Daily PVI history |
| `digests` | Generated digests |
| `calendar_events` | Calendar events from GCal |
| `focus_sessions` | Focus/DND history |
| `llm_runs` | Audit log of every LLM call |
