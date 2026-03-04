# Clawdbot Phase 4 — Zero Friction, Anywhere Access

> **Vision:** Everything works from your phone. The web dashboard has a real URL you can bookmark. The Telegram bot feels like a real assistant — you can read drafts, edit them, snooze tasks for a custom time, and search anything. Every feature that was "built but dormant" is connected and firing.

> **Active plan file:** `docs/plans/2026-03-04-clawdbot-phase4.md`
> **Resume from here if context clears.**

---

## PROGRESS TRACKER

- [ ] T1: Public web dashboard — Cloudflare Tunnel + API systemd service + HTTPS URL
- [ ] T2: Reply draft workflow — read + edit + send from Telegram
- [ ] T3: Interactive digest — task cards with buttons in morning digest
- [ ] T4: Variable snooze — custom duration from Telegram
- [ ] T5: Weekly auto-digest — scheduled Sunday 7pm Telegram send
- [ ] T6: GCal + meeting prep activation — connect calendar on VM
- [ ] T7: `/search` command — search tasks + messages from Telegram
- [ ] T8: Task editing from Telegram — change due date, priority, title
- [ ] T9: Dashboard v2 — reply drafts page, digest viewer, mobile layout
- [ ] T10: Reply draft surfacing — lower urgency threshold, always notify

---

## Honest Baseline (Phase 3 end state)

### What actually works today
| Feature | Works? | How |
|---------|--------|-----|
| Telegram bot (/tasks /inbox /digest /pvi /focus /newtask /status) | ✅ | Message your bot |
| Task cards with Accept/Dismiss/Done/Snooze | ✅ | Snooze hardcoded to 2h |
| Daily digest at 7am | ✅ | Automatic |
| Reminders pushed to Telegram | ✅ | Automatic |
| Focus mode | ✅ | /focus 30 or claw focus |
| Gmail polling + LLM extraction | ✅ | Every 5 min |
| PVI scoring | ✅ | Auto, see with /pvi |
| CLI (all claw commands) | ✅ | SSH only |

### What's built but not truly accessible
| Feature | Status | Blocker |
|---------|--------|---------|
| Web dashboard | Code done | No API systemd service, port closed, no domain |
| GCal + meeting prep | Code done | `claw connect gcal` never run on VM (needs browser) |
| Reply draft edit from Telegram | Partial | Can send/skip but can't read or edit draft text |
| Reply draft notifications | Partial | Only fires for high-urgency — most drafts never surface |
| Outlook | Code done | Needs Azure app registration + OUTLOOK_CLIENT_ID |
| Weekly digest | Code done | CLI only, no auto-schedule |

### Real gaps (not yet built)
| Gap | Why it matters |
|-----|---------------|
| Snooze is 2h fixed | Can't snooze to tomorrow, Friday, etc. |
| Digest tasks have no buttons | See tasks in digest but can't act on them |
| No task editing from Telegram | Can't change due date or priority after creation |
| No search from Telegram | Can't find a task without scrolling through /tasks |

---

## Architecture After Phase 4

```
┌─────────────────────────────────────────────────┐
│                   Sources                        │
│  Gmail · Outlook/NUS · Google Calendar · Canvas  │
└───────────────┬─────────────────────────────────┘
                │ delta poll (2 min)
                ▼
┌───────────────────────────────────────────────┐
│              Worker (APScheduler)              │
│  poll → normalize → triage → LLM extract      │
│  → tasks → reminders → meeting prep           │
│  → weekly digest (Sun 7pm)                    │
└────┬──────────────────────────────────────────┘
     │                         │
     ▼                         ▼
┌──────────┐         ┌──────────────────────────────┐
│ Postgres │         │       Telegram Bot            │
│ (Neon)   │         │  /tasks       — buttons       │
│          │         │  /replies     — read+edit+send│
│          │         │  /search      — keyword lookup│
│          │         │  /newtask     — conversational│
│          │         │  /snooze      — custom time   │
│          │         │  /edittask    — edit fields   │
│          │         │  digest       — with buttons  │
└──────────┘         └──────────────────────────────┘
     │                         │
     ▼                         ▼
┌────────────────────────────────────────────────────┐
│     FastAPI (public via Cloudflare Tunnel)          │
│                                                    │
│  /           — dashboard (PVI + tasks + inbox)     │
│  /tasks      — full list, accept/dismiss inline    │
│  /inbox      — messages + summaries               │
│  /replies    — draft emails, edit + send           │
│  /digest     — today's + weekly digest viewer      │
│  /focus      — toggle focus mode from browser      │
│                                                    │
│  URL: https://clawdbot-<hash>.trycloudflare.com    │
│  (or custom: https://ops.yourdomain.com)           │
└────────────────────────────────────────────────────┘
```

---

## Task 1: Public Web Dashboard

**Goal:** The dashboard has a real HTTPS URL reachable from any device — phone, laptop, anywhere — without VPN or SSH.

**Approach:** Cloudflare Tunnel (free, zero firewall changes, instant HTTPS). No domain purchase needed for basic setup. Can upgrade to a custom domain later.

**Why Cloudflare Tunnel over alternatives:**
- nginx + Let's Encrypt: requires open port 80/443 + domain + cert renewal
- ngrok: free tier URLs change on restart
- GCP firewall rule: HTTP only, no HTTPS without Load Balancer ($)
- Cloudflare Tunnel: free, persistent, HTTPS by default, no firewall changes, survives VM restarts

### Sub-task 1a: API server systemd service

**File to create:** `/etc/systemd/system/clawdbot-api.service` (on VM)

```ini
[Unit]
Description=Clawdbot API Server
After=network.target
[Service]
User=<vm_user>
WorkingDirectory=/home/<vm_user>/LifeOps
EnvironmentFile=/home/<vm_user>/LifeOps/.env
Environment=PYTHONPATH=/home/<vm_user>/LifeOps/packages/core/src:/home/<vm_user>/LifeOps/packages/connectors/src:/home/<vm_user>/LifeOps/packages/cli/src:/home/<vm_user>/LifeOps/apps/api/src
ExecStart=python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
```

Commands:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now clawdbot-api
sudo systemctl status clawdbot-api   # verify running
```

Also add `apps/api` to the auto-update cron restart list:
```bash
*/10 * * * * cd ~/LifeOps && git pull origin master --quiet && sudo systemctl restart clawdbot-bot clawdbot-worker clawdbot-api
```

### Sub-task 1b: Cloudflare Tunnel

On the VM:
```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Quick one-off tunnel (temporary URL — good for testing):
cloudflared tunnel --url http://localhost:8000
# → gives https://something.trycloudflare.com

# For a permanent named tunnel (requires free Cloudflare account + domain):
cloudflared login
cloudflared tunnel create clawdbot
cloudflared tunnel route dns clawdbot ops.yourdomain.com
```

Systemd service for persistent tunnel:
```ini
[Unit]
Description=Cloudflare Tunnel (Clawdbot)
After=network.target
[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8000
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
```

**Acceptance criteria:**
- [ ] `https://<tunnel-url>/` loads the dashboard in a browser without SSH
- [ ] `/tasks` page loads and shows real tasks from DB
- [ ] API server auto-restarts on VM reboot
- [ ] URL works from phone browser

---

## Task 2: Reply Draft Workflow (Read + Edit + Send from Telegram)

**Goal:** When a reply draft exists, you get a Telegram message showing the full draft text with three options: Send As-Is, Edit, Skip. If you tap Edit, the bot enters a conversation and you type your revised text, then confirm.

**Current state:** Bot sends a notification but you can't see the draft text or edit it — only blindly send or skip.

### Sub-task 2a: New `/replies` command

Show all pending reply drafts in Telegram. Each draft gets its own message with inline buttons.

**File:** `apps/bot/src/bot/handlers/commands.py`

Add `handle_replies`:
- Query `ReplyDraft` where `status = "pending"` for the user
- For each draft: show sender, subject, truncated body preview, then the draft text
- Buttons: `[✓ Send] [✏️ Edit] [✗ Skip]`
- Register as `/replies` CommandHandler in `main.py`

Format:
```
📧 From: prof@nus.edu.sg
Re: CS3230 midterm

Draft reply:
"Dear Prof, thank you for the update. I will submit by Friday. Best, Aryan"

[✓ Send As-Is]  [✏️ Edit]  [✗ Skip]
```

### Sub-task 2b: Edit flow (ConversationHandler)

**File:** `apps/bot/src/bot/handlers/callbacks.py` + `commands.py`

States: `REPLY_EDIT_TEXT = 10` (use high number to avoid conflict with NEWTASK states)

Flow:
1. User taps `✏️ Edit` on a reply card → callback `reply_edit:<draft_id>`
2. Bot enters conversation, stores `draft_id` in `context.user_data`
3. Bot says: "Type your revised reply below. Current draft:\n\n_{current text}_"
4. User sends new text
5. Bot shows preview: "Send this reply?\n\n_{new text}_\n\n[✓ Confirm] [↩ Re-edit] [✗ Cancel]"
6. User taps Confirm → update `ReplyDraft.draft_text`, then send via Gmail API
7. Bot confirms: "✓ Reply sent"

**Files to modify:**
- `apps/bot/src/bot/handlers/commands.py` — add `handle_replies`, edit conversation handlers
- `apps/bot/src/bot/handlers/callbacks.py` — add `reply_edit` callback route
- `apps/bot/src/bot/main.py` — add `/replies` CommandHandler + edit ConversationHandler
- `apps/bot/src/bot/keyboards.py` — add `build_reply_keyboard(draft_id)` with Send/Edit/Skip

### Sub-task 2c: Fix reply notification to always include draft text

**File:** `packages/core/src/core/reply_notify.py`

Currently sends: "Draft reply ready for [sender]" — user can't see what the draft says.

Update to include the first 200 chars of `draft_text` in the notification message itself.

**Acceptance criteria:**
- [ ] `/replies` lists all pending drafts with full text visible
- [ ] Tapping Edit enters a conversation; new text gets saved and sent
- [ ] Reply notification shows draft text preview (not just "draft ready")
- [ ] Confirmed sends actually fire Gmail API and mark draft as "sent"

---

## Task 3: Interactive Digest — Task Buttons in Morning Digest

**Goal:** The 7am digest currently lists tasks as plain text. Tasks should arrive as individual messages with the same Accept/Dismiss/Done/Snooze buttons as `/tasks`.

**Current state:** `send_digest(content_md)` sends one big Markdown block. No interaction.

**Approach:** Change `job_daily_pvi_and_digest` to:
1. Send the digest header (PVI, updates, upcoming) as one message
2. For each "do today" task: send a separate task card with inline keyboard (same as `/tasks`)

**Files to modify:**

`packages/core/src/core/digest/generator.py`
- Split return value: `generate_digest()` returns `(header_md, list[task_id])` instead of one string
- OR: keep `generate_digest()` as-is for storage/CLI, add `generate_digest_interactive()` that returns structured data

`apps/worker/src/worker/jobs.py` — `job_daily_pvi_and_digest()`
- After sending the header, iterate over do_today tasks
- For each task, call `send_task_notification()` (already exists in `core/telegram_notify.py`)

`packages/core/src/core/telegram_notify.py`
- Verify `send_task_notification()` correctly builds the inline keyboard with Accept/Dismiss/Done/Snooze
- It should use the same `build_task_keyboard()` pattern as the bot

**Key constraint:** The worker uses httpx (not python-telegram-bot), so inline keyboards must be sent via the raw Telegram Bot API (`sendMessage` with `reply_markup`). `send_message_with_keyboard()` in `telegram_client.py` already handles this.

**Acceptance criteria:**
- [ ] Morning digest starts with header block (PVI score, updates, upcoming)
- [ ] Each "do today" task arrives as a separate message with buttons
- [ ] Tapping buttons on digest tasks works identically to /tasks buttons
- [ ] If no do_today tasks, digest header says so (no orphan cards)

---

## Task 4: Variable Snooze

**Goal:** Tapping Snooze asks "Until when?" instead of silently scheduling +2 hours.

**Current state:** `snooze:<task_id>` callback hardcodes `+2 hours`.

**Approach:** Two-stage callback.

Stage 1 — Tap Snooze on task card:
- Edit the message: "⏰ Snooze until when?\n\n[1 hour] [3 hours] [Tomorrow morning] [Custom]"
- Callback data: `snooze_1h:<id>`, `snooze_3h:<id>`, `snooze_tom:<id>`, `snooze_custom:<id>`

Stage 2a — Preset buttons (1h/3h/tomorrow):
- Calculate `remind_at` from preset, create Reminder, confirm

Stage 2b — Custom:
- Enter ConversationHandler state `SNOOZE_CUSTOM`
- Bot: "When should I remind you? (e.g. 'Friday 5pm', 'tomorrow morning', '6h')"
- Parse with `dateparser`
- Create Reminder, confirm

**Files to modify:**
- `apps/bot/src/bot/handlers/callbacks.py` — replace `_snooze()` with `_snooze_menu()` + `_snooze_preset()` + `_snooze_custom()`
- `apps/bot/src/bot/handlers/commands.py` — add `SNOOZE_CUSTOM = 20` state constant
- `apps/bot/src/bot/main.py` — add snooze ConversationHandler for the custom branch
- `apps/bot/src/bot/keyboards.py` — add `build_snooze_menu(task_id)` keyboard

**Acceptance criteria:**
- [ ] Tapping Snooze shows a menu of options, not instant +2h
- [ ] Preset buttons (1h, 3h, tomorrow) work
- [ ] Custom option opens conversation, parses natural language time
- [ ] Reminder is created at the right time and fires as expected
- [ ] `/cancel` exits custom snooze cleanly

---

## Task 5: Weekly Auto-Digest (Sunday 7pm)

**Goal:** Every Sunday evening, the weekly review is automatically generated and pushed to Telegram — no manual `claw digest --weekly` needed.

**Current state:** `generate_weekly_review()` exists and is tested. No scheduled job.

**Files to modify:**

`apps/worker/src/worker/main.py`
- Add new APScheduler job: `job_weekly_digest` triggered by cron `day_of_week='sun', hour=19, minute=0`

`apps/worker/src/worker/jobs.py`
- Add `job_weekly_digest()`:
  ```python
  def job_weekly_digest():
      from core.digest.weekly import generate_weekly_review
      from core.telegram_client import send_digest
      with get_db() as db:
          user_ids = [str(u.id) for u in db.query(User).all()]
      for user_id in user_ids:
          content = generate_weekly_review(user_id)
          send_digest(content)
      log.info("weekly_digest_sent")
  ```

**Acceptance criteria:**
- [ ] Worker registers Sunday 7pm cron job
- [ ] `generate_weekly_review()` output is sent to Telegram on Sunday
- [ ] Can also be triggered manually via `/digest weekly` Telegram command or `claw digest --weekly`

---

## Task 6: GCal + Meeting Prep Activation

**Goal:** Google Calendar is connected on the VM so meeting prep fires 30 min before events.

**Problem:** `claw connect gcal` requires a browser, but the VM only has SSH.

**Solution — SSH local port forward:**
```bash
# On your local machine:
ssh -L 8080:localhost:8080 <vm-ip>

# On the VM (in the SSH session):
PYTHONPATH=... claw connect gcal
# This opens a browser prompt — paste the URL in your local browser
# The callback to localhost:8080 tunnels back through SSH to the VM
```

Alternative — generate on local machine and copy token:
```bash
# Local machine:
python3 -c "
import keyring, json, pathlib
data = keyring.get_password('clawdbot-gcal', 'token')
pathlib.Path('/tmp/gcal_token.json').write_text(data)
"
# Copy to VM using the base64 method (same as Gmail credentials)
```

**Verify meeting prep fires:**
```bash
# On VM, manually trigger:
PYTHONPATH=... python3 -c "
from core.calendar.prep import generate_prep_for_upcoming
from core.config import get_settings
msgs = generate_prep_for_upcoming(get_settings().default_user_id)
print(msgs)
"
```

**Files to verify (no code changes expected):**
- `packages/connectors/src/connectors/gcal/poller.py` — already implemented
- `packages/core/src/core/calendar/prep.py` — already implemented
- `apps/worker/src/worker/jobs.py:138-167` — `job_poll_gcal` + `job_meeting_prep` already registered

**Acceptance criteria:**
- [ ] `claw status` shows a gcal source with a recent `last_synced_at`
- [ ] Calendar events appear in `claw today` output
- [ ] Meeting prep Telegram message arrives ~30 min before a test calendar event
- [ ] GCal token persists across VM reboots (stored in `~/.config/clawdbot/tokens/`)

---

## Task 7: `/search` Command in Telegram

**Goal:** Type `/search buy milk` and get matching tasks and messages instantly.

**Scope:** Search both `ActionItem.title` and `Message.sender + Message.title + MessageSummary.summary_short`.

**Files to create/modify:**

`apps/bot/src/bot/handlers/commands.py` — add `handle_search`:
- Args: `context.args` joined as search query
- If no args, reply: "Usage: `/search <query>`"
- Query ActionItems: `ILIKE '%<query>%'` on title (case-insensitive)
- Query Messages: `ILIKE` on sender + title + body_preview
- Show tasks as task cards (with buttons), messages as simple text rows
- Limit: 5 tasks + 5 messages
- If nothing found: "No results for _<query>_"

`apps/bot/src/bot/main.py` — register `CommandHandler("search", commands.handle_search)`

**Database note:** SQLAlchemy `ilike()` on Postgres is efficient; no full-text index needed for personal-scale data.

Format:
```
🔍 Results for "buy milk"

Tasks (1):
• Buy milk from NTUC — 🟡 Medium | Due: Fri 06 Mar

Messages (0):
No matching messages.
```

**Acceptance criteria:**
- [ ] `/search` with no args returns usage hint
- [ ] `/search <query>` returns matching tasks with action buttons
- [ ] `/search <query>` returns matching messages as text
- [ ] Case-insensitive matching works
- [ ] Empty results handled gracefully

---

## Task 8: Task Editing from Telegram

**Goal:** After creating a task or viewing it in `/tasks`, you can edit the title, due date, or priority without dismissing and recreating.

**New bot command: `/edittask`**

Entry points:
1. `/edittask` — shows recent tasks to pick from
2. New inline button "✏️ Edit" on task cards (alongside Dismiss/Snooze/Done)

**Edit flow (ConversationHandler):**
State constants: `EDIT_CHOOSE_FIELD = 30`, `EDIT_INPUT_VALUE = 31`

1. User taps ✏️ Edit on a task card → callback `edit:<task_id>`
2. Bot: "What do you want to change?\n[📝 Title] [⏰ Due date] [🔢 Priority]"
3. User taps a field button
4. Bot: "Current title: _Buy milk_. Type the new title:"
5. User types new value
6. Bot updates DB, confirms: "✓ Updated."
7. Bot re-sends the updated task card with fresh data

**Priority input:** Accept `high`, `medium`, `low` (maps to 80, 50, 20) or a number 0–100.

**Due date input:** Parse with `dateparser` (same as `/newtask`).

**Files to modify:**
- `apps/bot/src/bot/handlers/commands.py` — add `handle_edittask_start`, `handle_edit_field_choice`, `handle_edit_value`, `handle_edit_cancel`
- `apps/bot/src/bot/handlers/callbacks.py` — add `edit` callback route
- `apps/bot/src/bot/keyboards.py` — add ✏️ Edit button to task keyboard (for active tasks); add `build_edit_field_keyboard(task_id)`
- `apps/bot/src/bot/main.py` — add edit ConversationHandler

**Acceptance criteria:**
- [ ] ✏️ Edit button appears on task cards
- [ ] Can change title, due date, or priority individually
- [ ] After edit, updated task card is shown with correct new values
- [ ] `/cancel` exits edit flow at any point
- [ ] Invalid priority values give a clear error and reprompt

---

## Task 9: Dashboard v2

**Goal:** The web dashboard is genuinely useful — covers everything you'd want to check from a browser that you can't quickly do in Telegram.

**New pages and improvements:**

### 9a: Reply Drafts Page (`/replies`)
- List all pending `ReplyDraft` rows
- Show: sender, subject, full draft text, tone
- Buttons: Send (POST /api/replies/{id}/send), Edit (inline text area), Skip
- Edit inline: clicking Edit replaces the draft text with a `<textarea>`, type new text, click Save → updates DB

**Files:**
- `apps/api/src/api/routes/dashboard_api.py` — add `GET /api/replies`, `POST /api/replies/{id}/send`, `POST /api/replies/{id}/dismiss`, `POST /api/replies/{id}/update`
- `apps/api/src/api/templates/replies.html` — new template
- `apps/api/src/api/main.py` — add `/replies` page route

### 9b: Digest Viewer Page (`/digest`)
- Show today's digest as formatted HTML (render the Markdown)
- Button: "Regenerate" → POST /api/digest/generate
- Tab: "Weekly" → shows weekly review

**Files:**
- `apps/api/src/api/routes/dashboard_api.py` — add `GET /api/digest/today`, `GET /api/digest/weekly`, `POST /api/digest/generate`
- `apps/api/src/api/templates/digest.html` — new template

### 9c: Focus Toggle on Dashboard (`/`)
- Dashboard homepage shows Focus Mode status
- Toggle button: "Start Focus" / "End Focus" — updates DB via POST
- Shows time remaining if active

**Files:**
- `apps/api/src/api/routes/dashboard_api.py` — add `GET /api/focus/status`, `POST /api/focus/start`, `POST /api/focus/end`
- `apps/api/src/api/templates/dashboard.html` — add focus block

### 9d: Navigation bar
- Add a proper nav bar to `base.html`: Dashboard | Tasks | Inbox | Replies | Digest
- Mobile-responsive (Tailwind flex)

### 9e: Better task page
- Show all statuses (proposed + active), not just proposed
- Sort by priority + due date
- Show priority label (🔴/🟡/🟢) and overdue indicator (⚠️)

**Acceptance criteria:**
- [ ] `/replies` page loads drafts and Send/Skip work
- [ ] Inline editing of draft text works and persists
- [ ] `/digest` shows today's digest rendered as HTML
- [ ] Focus toggle on homepage updates DB and shows correct state
- [ ] Nav bar present on all pages, works on mobile

---

## Task 10: Reply Draft Surfacing — Always Notify

**Goal:** Every reply draft that gets generated should reach you in Telegram, not just high-urgency ones.

**Current state:** `telegram_notify.py` only sends a reply notification if urgency > some threshold or if explicitly called. Most drafts are generated silently.

**Files to check/modify:**

`packages/core/src/core/llm/extractor.py`
- Find where `ReplyDraft` rows are created (around line 318-324)
- Find where `send_reply_notification()` is called — check the condition
- Remove or lower the urgency threshold: notify for ALL drafts

`packages/core/src/core/reply_notify.py`
- Update notification format to include the first 200 chars of draft text:
  ```
  📧 Draft reply ready
  To: prof@nus.edu.sg
  Re: CS3230 midterm

  "Dear Prof, thank you for the update..."

  [✓ Send]  [✏️ Edit]  [✗ Skip]
  ```
- Use `build_reply_keyboard(draft_id)` from `bot/keyboards.py`
- Ensure the keyboard uses correct callback format: `reply_send:<id>`, `reply_edit:<id>`, `reply_skip:<id>`

**Note:** `reply_notify.py` uses httpx directly (not python-telegram-bot), so the keyboard must be sent as raw JSON via `send_message_with_keyboard()`.

**Acceptance criteria:**
- [ ] Every generated reply draft triggers a Telegram notification
- [ ] Notification shows sender, subject, and first 200 chars of draft text
- [ ] Send / Edit / Skip buttons are present and functional
- [ ] Edit button triggers the T2 edit flow

---

## Implementation Order & Dependencies

```
T1 (public dashboard)   → unblocks T9 (dashboard v2 actually accessible)
T2 (reply edit)         → required for T10 (reply always notify) — edit button needs edit flow
T10 (always notify)     → requires T2 edit flow to be in place first
T4 (variable snooze)    → standalone, no dependencies
T5 (weekly auto)        → standalone, no dependencies
T6 (gcal activation)    → standalone setup, no code changes
T7 (search)             → standalone, no dependencies
T3 (interactive digest) → standalone but benefits from T4 (snooze options on digest tasks)
T8 (task edit)          → standalone, no dependencies
T9 (dashboard v2)       → depends on T1 (accessible URL) and ideally T2 (replies page needs edit API)
```

**Recommended execution order:**
1. T1 → get the URL first (everything else benefits from being accessible)
2. T5, T4, T7 → quick wins, no dependencies
3. T2 → reply edit (needed before T10)
4. T10 → reply surfacing
5. T3 → interactive digest
6. T6 → gcal setup
7. T8 → task editing
8. T9 → dashboard v2 (last, benefits from all API additions above)

---

## Files Summary

### New files to create
| File | Purpose |
|------|---------|
| `/etc/systemd/system/clawdbot-api.service` | API server persistent service (VM) |
| `/etc/systemd/system/clawdbot-tunnel.service` | Cloudflare Tunnel persistent service (VM) |
| `apps/api/src/api/templates/replies.html` | Reply drafts page |
| `apps/api/src/api/templates/digest.html` | Digest viewer page |

### Files to modify
| File | Changes |
|------|---------|
| `apps/bot/src/bot/handlers/commands.py` | Add: handle_replies, handle_search, handle_edittask_*, SNOOZE_CUSTOM, EDIT_* state constants |
| `apps/bot/src/bot/handlers/callbacks.py` | Add: reply_edit callback, _snooze_menu, _snooze_preset, _snooze_custom, edit callback |
| `apps/bot/src/bot/keyboards.py` | Add: build_reply_keyboard, build_snooze_menu, build_edit_field_keyboard; add ✏️ Edit to task keyboard |
| `apps/bot/src/bot/main.py` | Add: /replies, /search, /edittask handlers + ConversationHandlers for snooze_custom, edit, reply_edit |
| `apps/worker/src/worker/jobs.py` | Add: job_weekly_digest() |
| `apps/worker/src/worker/main.py` | Register: job_weekly_digest Sunday 7pm cron |
| `packages/core/src/core/reply_notify.py` | Add draft text preview, lower urgency threshold, add Edit button |
| `packages/core/src/core/llm/extractor.py` | Always call send_reply_notification() when draft created |
| `packages/core/src/core/digest/generator.py` | Add generate_digest_interactive() returning structured data |
| `apps/worker/src/worker/jobs.py` | Update job_daily_pvi_and_digest() to send task cards with buttons |
| `apps/api/src/api/routes/dashboard_api.py` | Add: /api/replies, /api/focus, /api/digest endpoints |
| `apps/api/src/api/main.py` | Add: /replies, /digest page routes |
| `apps/api/src/api/templates/base.html` | Add: nav bar |
| `apps/api/src/api/templates/dashboard.html` | Add: focus toggle block |
| `apps/api/src/api/templates/tasks.html` | Show all statuses, priority labels, overdue indicator |

---

## Success Criteria (Phase 4 Complete)

- [ ] Dashboard reachable at a real HTTPS URL from any device without SSH
- [ ] Every reply draft shows up in Telegram with full text + Send/Edit/Skip
- [ ] Morning digest tasks are interactive (tappable buttons)
- [ ] Snooze lets you pick duration (not hardcoded 2h)
- [ ] Weekly review auto-sends every Sunday
- [ ] GCal is connected and meeting prep fires
- [ ] `/search` works from Telegram
- [ ] Tasks can be edited (title/due date/priority) from Telegram
- [ ] Dashboard has reply drafts, digest viewer, and focus toggle
- [ ] All features accessible without any CLI or SSH in normal daily use
