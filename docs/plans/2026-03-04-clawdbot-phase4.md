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
- [ ] T11: Inbox account tagging — show which email address each message was delivered to
- [ ] T12: Multi-account Gmail — connect 2+ Gmail addresses, each polled and tagged independently

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
| Only one Gmail account | Can't monitor personal + work Gmail simultaneously |
| Snooze is 2h fixed | Can't snooze to tomorrow, Friday, etc. |
| Digest tasks have no buttons | See tasks in digest but can't act on them |
| No task editing from Telegram | Can't change due date or priority after creation |
| No search from Telegram | Can't find a task without scrolling through /tasks |

---

## Architecture After Phase 4

```
┌─────────────────────────────────────────────────┐
│                        Sources                             │
│  Gmail (personal) · Gmail (work) · Outlook/NUS · GCal     │
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

## Task 11: Inbox Account Tagging

**Goal:** Every message in `/inbox`, the digest, and the web dashboard shows which email address it was delivered to — so you instantly know if something came to your Gmail, NUS Outlook, or any other connected account.

**Why it matters:** Once multiple sources are connected (Gmail + Outlook/NUS), the inbox becomes a mix of emails from different accounts with no indication of which is which. A message from "admin@nus.edu.sg" looks the same whether it was in your personal Gmail or your NUS Outlook.

**Current state:** The `Source` table has `display_name` ("Gmail", "Outlook/NUS") and `source_type` ("gmail", "outlook"). Every `Message` has a `source_id` foreign key. The information is there — it just isn't surfaced anywhere in the UI.

### Sub-task 11a: Telegram `/inbox` command

**File:** `apps/bot/src/bot/handlers/commands.py` — `handle_inbox`

Current format:
```
* prof@nus.edu.sg: Assignment due Friday
```

New format — prefix each line with account tag:
```
[Gmail] prof@nus.edu.sg: Assignment due Friday
[NUS Outlook] admin@nus.edu.sg: IT maintenance tonight
```

Implementation:
- Inside the `with get_db()` block, join `Message` → `Source` to get `source.display_name`
- Or: query `Source` by `source_id` for each message
- Prepend `[{source.display_name}]` to each inbox line
- Escape for MarkdownV2

### Sub-task 11b: Morning digest

**File:** `packages/core/src/core/digest/generator.py`

In the `## UPDATES` section, prefix each message line with the source:
```
• [Gmail] prof@nus.edu.sg: Assignment due Friday
• [NUS Outlook] admin@nus.edu.sg: IT maintenance tonight
```

Implementation:
- Join `Message → Source` in the `recent_messages` query (already joins `MessageSummary`)
- Add `Source` to the join: `.join(Source, Source.id == Message.source_id, isouter=True)`
- Pass `source.display_name` (or `source.source_type` as fallback) into the line formatter

### Sub-task 11c: Web dashboard inbox page

**File:** `apps/api/src/api/routes/dashboard_api.py` — `get_messages()`

Add `source_display_name` to the returned dict for each message:
```python
"source": source.display_name if source else "Unknown",
```

**File:** `apps/api/src/api/templates/inbox.html`

Display as a badge next to the sender: `<span class="badge">[Gmail]</span> prof@nus.edu.sg`

### Sub-task 11d: Source display name normalisation

When accounts are connected, `display_name` is set as "Gmail", "Outlook/NUS", "Google Calendar". For the inbox tag, use short canonical labels:

| `source_type` | Tag shown |
|---------------|-----------|
| `gmail` | `Gmail` |
| `outlook` | `NUS Outlook` |
| `gcal` | *(calendar, not shown in inbox)* |

A simple helper in `core/db/models.py` or inline in each view:
```python
def _source_tag(source_type: str, display_name: str) -> str:
    return display_name or source_type.title()
```

**Files to modify:**
- `apps/bot/src/bot/handlers/commands.py` — update `handle_inbox` to join source
- `packages/core/src/core/digest/generator.py` — join Source in recent_messages query, prefix lines
- `apps/api/src/api/routes/dashboard_api.py` — add `source` field to messages response
- `apps/api/src/api/templates/inbox.html` — render source badge

**Acceptance criteria:**
- [ ] `/inbox` in Telegram shows `[Gmail]` or `[NUS Outlook]` prefix on each message
- [ ] Morning digest updates section shows account tag per message
- [ ] Web dashboard inbox shows source badge next to sender
- [ ] If source is unknown (orphaned message), shows nothing rather than crashing
- [ ] Works correctly when only one source is connected (tag still shown for clarity)

---

## Task 12: Multi-Account Gmail

**Goal:** Connect 2+ Gmail addresses and have every inbox, digest, task, and notification correctly attributed to the right account. Run `claw connect gmail --label personal` and `claw connect gmail --label work` — both poll independently, both appear in `/inbox` with the right tag, both feed the LLM pipeline separately.

**Why it matters:** Right now `claw connect gmail` overwrites the previous token. A second connect silently replaces the first. Multi-account support is the prerequisite for T11 to be meaningful when you have more than one Gmail.

---

### Sub-task 12a: Token storage keyed by account label

**File:** `packages/connectors/src/connectors/gmail/auth.py`

Current: `TOKEN_USERNAME = "default"` — one fixed key, overwritten on every connect.

New: `get_credentials(account_label: str)` and `run_oauth_flow(credentials_file, account_label)` — token stored under the label (e.g. `"personal"`, `"work"`).

After OAuth completes, call the Gmail API to discover the authenticated email address and store it in the token dict:

```python
from googleapiclient.discovery import build

def _get_email_address(creds) -> str:
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]
```

Store pattern:
```python
store_token(SERVICE_NAME, account_label, {
    "token": ...,
    "email": email_address,   # ← new field
    ...
})
```

**Why label, not email, as the key?** Email addresses can change (alias, rename). A stable user-chosen label is more robust. The email is stored *inside* the token dict for display and deduplication.

---

### Sub-task 12b: `claw connect gmail --label` flag

**File:** `packages/cli/src/cli/commands/connect.py`

```python
@app.command("gmail")
def connect_gmail(
    credentials: str = typer.Option("~/.config/clawdbot/gmail_credentials.json", ...),
    label: str = typer.Option("default", "--label", "-l",
        help="Account label, e.g. 'personal' or 'work'. Use a different label per Gmail account."),
):
```

After OAuth, fetch email address from the token dict. Register (or update) a `Source` row:

```python
with get_db() as db:
    existing = db.query(Source).filter_by(
        user_id=settings.default_user_id,
        source_type="gmail",
        display_name=f"Gmail ({label})",   # unique per label
    ).first()
    if not existing:
        db.add(Source(
            user_id=settings.default_user_id,
            source_type="gmail",
            display_name=f"Gmail ({label})",
            config_json={"account_label": label, "email": email_address},
        ))
```

**Idempotent:** Running the same label twice updates the existing `Source`, doesn't duplicate.

**Backwards compat:** Existing `Source` rows with `display_name="Gmail"` (old single-account) are left untouched — they continue to work using `account_label="default"` from config_json (or fallback to `"default"`).

---

### Sub-task 12c: Poller loads credentials per source

**File:** `packages/connectors/src/connectors/gmail/poller.py`

Current signature:
```python
def poll_gmail(user_id: str, source_id: str) -> None:
```

The poller calls `get_credentials()` with no account info — always loads the default token.

New: query `Source.config_json` for the account label, then pass it to `get_credentials`:

```python
def poll_gmail(user_id: str, source_id: str) -> None:
    from core.db.engine import get_db
    from core.db.models import Source
    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        account_label = (source.config_json or {}).get("account_label", "default")
    creds = get_credentials(account_label)
    ...
```

This change is purely additive — the `"default"` fallback means existing single-account setups keep working without any migration.

---

### Sub-task 12d: `claw status` shows all Gmail accounts

**File:** `packages/cli/src/cli/commands/status.py`

Currently shows one row per source type. With multi-account, show each Gmail source as its own row:

```
Sources:
  Gmail (personal)    ✓ connected   last sync: 2 min ago  (user@gmail.com)
  Gmail (work)        ✓ connected   last sync: 3 min ago  (work@company.com)
  Outlook/NUS         ✓ connected   last sync: 5 min ago
```

Pull `email` from `source.config_json` for the display.

---

### Sub-task 12e: Deduplication guard

**Problem:** If someone connects the same Gmail twice under different labels, messages get ingested twice.

**Solution:** In `poller.py`, after fetching message IDs from Gmail, check `external_id` against the `RawEvent` table (already done). No extra work needed — the existing `external_id` dedup covers this case.

Additionally, in `connect_gmail`, warn if the discovered email is already registered under a different label:

```python
# Check for duplicate email across all Gmail sources
existing_emails = [
    s.config_json.get("email") for s in db.query(Source)
    .filter_by(user_id=..., source_type="gmail").all()
    if s.config_json
]
if email_address in existing_emails:
    rprint(f"[yellow]Warning: {email_address} is already connected under a different label.[/yellow]")
```

---

### Sub-task 12f: `/inbox` and digest use display_name from Source

This directly feeds T11. With multi-account Gmail, `source.display_name` will be `"Gmail (personal)"` or `"Gmail (work)"`, so T11's account tags become genuinely meaningful:

```
[Gmail (personal)] prof@nus.edu.sg: Assignment due Friday
[Gmail (work)]     hr@company.com: Interview scheduled
[NUS Outlook]      admin@nus.edu.sg: IT maintenance
```

No extra work needed in T11 — it reads `source.display_name`, which T12 sets correctly.

---

### Sub-task 12g: `claw connect gmail --list` to show connected accounts

```python
@app.command("gmail")
def connect_gmail(
    ...
    list_accounts: bool = typer.Option(False, "--list", help="List connected Gmail accounts"),
):
    if list_accounts:
        with get_db() as db:
            sources = db.query(Source).filter_by(
                user_id=settings.default_user_id, source_type="gmail"
            ).all()
        for s in sources:
            email = (s.config_json or {}).get("email", "unknown")
            label = (s.config_json or {}).get("account_label", "default")
            rprint(f"  [{label}] {email} — {s.display_name}")
        return
```

---

### Setup flow (user-facing)

```bash
# First Gmail account
claw connect gmail --label personal
# → opens browser, authenticate with personal@gmail.com
# → ✓ Gmail (personal) connected (personal@gmail.com)

# Second Gmail account
claw connect gmail --label work
# → opens browser, authenticate with work@company.com
# → ✓ Gmail (work) connected (work@company.com)

# See all connected accounts
claw connect gmail --list
#   [personal] personal@gmail.com — Gmail (personal)
#   [work]     work@company.com   — Gmail (work)

# Outlook (unchanged)
claw connect outlook
```

---

### Files to modify

| File | Change |
|------|--------|
| `packages/connectors/src/connectors/gmail/auth.py` | `get_credentials(account_label)`, `run_oauth_flow(..., account_label)`, `_get_email_address(creds)` |
| `packages/connectors/src/connectors/gmail/poller.py` | Read `account_label` from `source.config_json`, pass to `get_credentials` |
| `packages/cli/src/cli/commands/connect.py` | Add `--label` + `--list` flags, store email in config_json, duplicate email warning |
| `packages/cli/src/cli/commands/status.py` | Show each Gmail source as separate row with email |

### Tests to add

- `tests/unit/test_gmail_multi_account.py`:
  - `test_connect_gmail_stores_account_label` — Source row has correct config_json
  - `test_connect_gmail_duplicate_label_updates_not_duplicates` — idempotent
  - `test_connect_gmail_duplicate_email_warns` — warning when same email on different label
  - `test_poll_gmail_uses_correct_credentials` — poller reads label from source.config_json

**Acceptance criteria:**
- [ ] `claw connect gmail --label personal` + `claw connect gmail --label work` both register separate Source rows
- [ ] Each source polls independently using its own credentials
- [ ] Same Gmail account connected twice under different labels shows a warning
- [ ] `claw status` lists both accounts with email addresses
- [ ] `claw connect gmail --list` shows all connected Gmail accounts
- [ ] `/inbox` tags show `[Gmail (personal)]` / `[Gmail (work)]` (via T11)
- [ ] Re-running `claw connect gmail --label personal` updates the token, doesn't create a duplicate Source row
- [ ] Old single-account setups (no label) continue to work unchanged

---

## Implementation Order & Dependencies

```
T1  (public dashboard)   → unblocks T9 (dashboard v2 actually accessible)
T2  (reply edit)         → required for T10 (reply always notify) — edit button needs edit flow
T10 (always notify)      → requires T2 edit flow to be in place first
T4  (variable snooze)    → standalone, no dependencies
T5  (weekly auto)        → standalone, no dependencies
T6  (gcal activation)    → standalone setup, no code changes
T7  (search)             → standalone, no dependencies
T3  (interactive digest) → standalone but benefits from T4 (snooze options on digest tasks)
T8  (task edit)          → standalone, no dependencies
T9  (dashboard v2)       → depends on T1 (accessible URL) and ideally T2 (replies page needs edit API)
T12 (multi-account Gmail)→ prerequisite for T11 to show multiple Gmail tags; standalone otherwise
T11 (account tagging)    → depends on T12 to be fully meaningful (multiple Gmail accounts registered)
```

**Recommended execution order:**
1. T1  → get the URL first (everything else benefits from being accessible)
2. T12 → multi-account Gmail (do early so T11 is immediately useful)
3. T5, T4, T7 → quick wins, no dependencies
4. T11 → account tagging (meaningful now that T12 added multiple sources)
5. T2  → reply edit (needed before T10)
6. T10 → reply surfacing
7. T3  → interactive digest
8. T6  → gcal setup
9. T8  → task editing
10. T9 → dashboard v2 (last, benefits from all API additions above)

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
| `apps/worker/src/worker/jobs.py` | Add: job_weekly_digest(); update job_daily_pvi_and_digest() to send task cards with buttons |
| `apps/worker/src/worker/main.py` | Register: job_weekly_digest Sunday 7pm cron |
| `packages/core/src/core/reply_notify.py` | Add draft text preview, lower urgency threshold, add Edit button |
| `packages/core/src/core/llm/extractor.py` | Always call send_reply_notification() when draft created |
| `packages/core/src/core/digest/generator.py` | Add generate_digest_interactive() returning structured data; join Source for account tags |
| `packages/connectors/src/connectors/gmail/auth.py` | get_credentials(account_label), run_oauth_flow(..., account_label), _get_email_address |
| `packages/connectors/src/connectors/gmail/poller.py` | Read account_label from source.config_json, pass to get_credentials |
| `packages/cli/src/cli/commands/connect.py` | Add --label + --list flags, store email in config_json, duplicate email warning |
| `packages/cli/src/cli/commands/status.py` | Show each Gmail source as separate row with email address |
| `apps/api/src/api/routes/dashboard_api.py` | Add: /api/replies, /api/focus, /api/digest endpoints; add source field to messages |
| `apps/api/src/api/main.py` | Add: /replies, /digest page routes |
| `apps/api/src/api/templates/base.html` | Add: nav bar |
| `apps/api/src/api/templates/dashboard.html` | Add: focus toggle block |
| `apps/api/src/api/templates/tasks.html` | Show all statuses, priority labels, overdue indicator |
| `apps/api/src/api/templates/inbox.html` | Add source badge next to sender |

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
- [ ] 2 Gmail + 1 Outlook all connected, polling, and tagged independently
- [ ] `/inbox` shows `[Gmail (personal)]` / `[Gmail (work)]` / `[NUS Outlook]` per message
- [ ] All features accessible without any CLI or SSH in normal daily use
