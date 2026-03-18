# Clawdbot Phase 4 — Design Spec
**Date:** 2026-03-19
**Status:** Approved
**Scope:** Telegram UX overhaul · Backend features · Next.js web app

---

## 1. Overview

Phase 4 makes Clawdbot accessible from anywhere — browser, phone, Telegram — without SSH or CLI. Three parallel tracks:

1. **Telegram UX overhaul** — better message formatting + full interactivity
2. **Backend features** — multi-account Gmail, weekly digest job, search
3. **Clawdbot Web App** — Next.js 16 replacement for the Jinja2 dashboard

The FastAPI REST backend stays unchanged. Only the frontend changes (Jinja2 → Next.js).

---

## 2. Telegram UX Overhaul

### 2.1 Message Style System

Three distinct styles, each used for its purpose:

**Style A — Clean Card** (task reminders, `/tasks`, meeting prep)
- Dark bg `#1e1e2e`, structured 3-field layout
- Fields: title, priority + due date, source
- Buttons: ✓ Done · ⏰ Snooze · ✗ Dismiss · ✏️ Edit
- Low cognitive load — fast action

**Style B — Information-Rich** (reply drafts)
- Left border = urgency colour (red/amber/green)
- Shows: sender, subject, first 200 chars of draft, confidence
- Buttons: ✓ Send · ✏️ Edit · ✗ Skip
- Context-heavy — user needs it before approving a reply

**Style C — Grouped Digest** (morning digest, weekly review)
- Single message with full picture
- Header: PVI score + regime
- Sections: 📌 DO TODAY · 📅 UPCOMING · 🔄 UPDATES
- Emoji colour-coding: 🔴 urgent · 🟡 medium · 🟢 low
- Footer: unread count · overdue count · focus status
- Morning digest: header (Style C) → individual task cards (Style A) as separate messages

### 2.2 Interactive Features (Phase 4 tasks)

| Feature | What changes |
|---------|-------------|
| **T2 — Reply workflow** | `/replies` command + Edit conversation flow (show full draft, 3-stage: view → edit → confirm) |
| **T3 — Interactive digest** | Split digest into header (Style C) + per-task cards (Style A) with buttons |
| **T4 — Variable snooze** | Snooze menu: 1h · 3h · Tomorrow morning · Custom (natural language via dateparser) |
| **T7 — Search** | `/search <query>` — ILIKE on tasks + messages, returns task cards + message rows |
| **T8 — Task edit** | ✏️ Edit button on task cards → choose field → type value → confirm |
| **T10 — Always notify** | Every reply draft triggers Telegram notification (remove urgency threshold) |
| **T11 — Account tagging** | `[Gmail]` / `[NUS Outlook]` prefix on inbox lines, digest updates, task source field |

---

## 3. Backend Features

### 3.1 T5 — Weekly Auto-Digest
- APScheduler cron: Sunday 19:00 SGT
- Calls existing `generate_weekly_review()` → sends via `send_digest()`
- Also triggerable via `/digest weekly` Telegram command

### 3.2 T12 — Multi-Account Gmail
- `claw connect gmail --label personal` / `--label work`
- Token keyed by label; email address stored in `source.config_json`
- Poller reads `account_label` from `source.config_json` → loads correct credentials
- Dedup guard: warn if same email registered under different label
- `claw connect gmail --list` shows all connected accounts
- `claw status` lists each Gmail source as separate row with email

### 3.3 T6 — GCal Activation (infrastructure, not code)
- SSH local port forward to connect gcal on VM
- Verify `job_poll_gcal` + `job_meeting_prep` fire correctly
- Meeting prep: Style A card pushed 30 min before events

### 3.4 T1 — Public Access (infrastructure)
- `clawdbot-api.service` systemd unit (uvicorn on port 8000)
- Cloudflare Tunnel → persistent HTTPS URL
- Auto-restart on VM reboot

---

## 4. Clawdbot Web App (Next.js)

### 4.1 Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Framework | Next.js 16 (App Router) | RSC, mobile-first, zero-config deploy |
| UI library | shadcn/ui + Tailwind | Dark mode, composable, design system |
| Data fetching | SWR | Client-side polling, auto-revalidate |
| Backend | FastAPI REST (unchanged) | Same endpoints, no migration needed |
| Auth | API key header (existing `dashboard_api_key`) | Simple, already implemented |
| Hosting | Static export via Cloudflare Tunnel OR Vercel | TBD based on deployment setup |

### 4.2 Design System

**Colours:**
```
bg:          #0f1117
sidebar:     #13151f
card:        #1a1d27
border:      rgba(255,255,255,0.06)
accent:      #7c3aed
accent-light:#a78bfa
text:        #e2e8f0
muted:       #6c7086
urgent:      #f87171
medium:      #fbbf24
low/done:    #34d399
```

**Typography:** Geist Sans (UI) · Geist Mono (IDs, timestamps, PVI score)

**Sidebar:** 48px wide, icon-only. Slide-out pill tooltip on hover (label appears right of icon, purple-tinted, disappears on mouse-out). Active page: icon bg `#1e2130` + purple icon colour.

**Mobile:** Sidebar hidden. Bottom nav bar with icon + label (Tasks · Inbox · Digest · Replies · Focus). Search accessible via 🔍 icon in top bar.

**Task rows:**
- Checkbox with urgency-coloured border (red/amber/green)
- Active tasks: full opacity, coloured border
- Proposed tasks: 70% opacity, Accept + Dismiss inline buttons
- Done tasks: strikethrough, 45% opacity, green checkmark

**Status chips (top bar):**
- PVI chip: purple glow ring + score + regime
- Worker chip: green glow dot + "Worker"
- Both use `box-shadow: 0 0 8px rgba(color, 0.15)`

### 4.3 Pages

#### `/tasks` (default landing)
- Filter tabs: All · Today · Overdue · Proposed
- Task rows: checkbox · title · source · due date · priority badge · `···` menu
- `···` menu: Edit title / Edit due / Edit priority / Snooze / View source message
- Snooze picker: 1h · 3h · Tomorrow · Custom (date input)
- `+ New task` button → slide-in drawer with title, due, priority fields
- Bottom stat bar: N active · N overdue · N proposed · N done today

#### `/inbox`
- Source filter: All · Gmail (personal) · Gmail (work) · NUS Outlook
- Message rows: source badge · sender · subject · summary preview · timestamp
- Click → expand panel: full summary, extracted action items with Accept/Dismiss, reply draft if exists
- Unread indicator dot

#### `/digest`
- Today tab: PVI score card + regime description + 7-day sparkline
- Sections: Do Today · Upcoming · Updates (same structure as Telegram Style C)
- Task cards inline with buttons (same as `/tasks` rows)
- Regenerate button (POST /api/digest/generate)
- Weekly tab: weekly review rendered as formatted HTML

#### `/replies`
- List of pending reply drafts
- Each card: sender · subject · full draft text · tone badge
- Edit mode: click Edit → textarea replaces draft text → Save
- Send button: POST /api/replies/{id}/send → mark sent → remove from list
- Skip button: dismiss draft
- Sent tab: history of sent replies

#### `/search`
- Auto-focused search input on page load
- Debounced ILIKE query (300ms) against tasks + messages
- Task results: same task row component as `/tasks`
- Message results: sender · subject · summary snippet with match highlighted
- Empty state: "No results for X"

#### `/focus`
- Large toggle: Start Focus / End Focus
- Duration picker: 25m · 45m · 90m · Custom
- Countdown timer (large, centre-screen) when active
- PVI card + worker status
- Quick stats: tasks done today · emails processed today

### 4.4 Component Architecture

```
app/
  layout.tsx          — root layout, sidebar, bottom nav (mobile)
  page.tsx            — redirect to /tasks
  tasks/page.tsx
  inbox/page.tsx
  digest/page.tsx
  replies/page.tsx
  search/page.tsx
  focus/page.tsx

components/
  layout/
    Sidebar.tsx       — icon nav, slide-out tooltips, active state
    BottomNav.tsx     — mobile bottom nav
    TopBar.tsx        — PVI chip, worker chip, search icon (mobile)
  tasks/
    TaskRow.tsx       — checkbox, fields, priority badge, ··· menu
    SnoozePicker.tsx  — duration options + custom date input
    NewTaskDrawer.tsx — slide-in form
  inbox/
    MessageRow.tsx    — source badge, preview, expand panel
    SourceFilter.tsx  — filter tabs
  digest/
    PVICard.tsx       — score, regime, 7-day sparkline
    DigestSection.tsx — Do Today / Upcoming / Updates sections
  replies/
    ReplyCard.tsx     — draft text, inline edit textarea, Send/Skip
  shared/
    StatusChip.tsx    — PVI chip / Worker chip with glow
    PriorityBadge.tsx — 🔴/🟡/🟢 + label
    SourceBadge.tsx   — [Gmail] / [NUS Outlook] badge

lib/
  api.ts              — typed wrappers for all FastAPI endpoints
  swr-hooks.ts        — useTasks, useMessages, useDigest, usePVI, useReplies
```

### 4.5 API Integration

All data via SWR hooks hitting existing FastAPI endpoints. New endpoints needed:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/replies` | GET | List pending drafts |
| `/api/replies/{id}/send` | POST | Send via Gmail |
| `/api/replies/{id}/dismiss` | POST | Skip draft |
| `/api/replies/{id}/update` | POST | Save edited text |
| `/api/digest/today` | GET | Today's digest JSON |
| `/api/digest/weekly` | GET | Weekly review JSON |
| `/api/digest/generate` | POST | Regenerate today's digest |
| `/api/focus/status` | GET | Active focus session |
| `/api/focus/start` | POST | Start focus (duration param) |
| `/api/focus/end` | POST | End focus session |
| `/api/search` | GET | `?q=<query>` tasks + messages |

Existing endpoints (`/api/tasks`, `/api/messages`, `/api/pvi/today`) stay unchanged.

---

## 5. Implementation Order

```
Week 1 — Infrastructure + Quick wins
  T1:  Public access (systemd + Cloudflare Tunnel)
  T5:  Weekly auto-digest (1 job, ~30 min)
  T11: Account tagging (join Source in queries)
  T6:  GCal activation (SSH setup, no code)

Week 2 — Telegram interactivity
  T12: Multi-account Gmail
  T4:  Variable snooze
  T2:  Reply draft workflow (edit flow)
  T10: Always notify on reply draft

Week 3 — Telegram remaining + web foundation
  T7:  Search command
  T8:  Task edit from Telegram
  T3:  Interactive digest (task cards)
  Next.js scaffold + design system + /tasks page

Week 4 — Web app pages
  /inbox + /digest + /replies + /search + /focus
  Mobile layout (bottom nav)
  New FastAPI endpoints
  SWR hooks + API layer
```

---

## 6. Out of Scope (Phase 4)

- Outlook (Azure app registration not yet set up — Phase 5)
- Canvas API polling (Phase 5)
- Real-time WebSocket updates (polling via SWR is sufficient)
- Auth system beyond API key (single-user app)
- Dark/light mode toggle (dark only for Phase 4)

---

## 7. Success Criteria

- [ ] Dashboard at real HTTPS URL from any device without SSH
- [ ] All reply drafts surface in Telegram with full text + Send/Edit/Skip
- [ ] Morning digest tasks are interactive (tappable buttons)
- [ ] Snooze lets you pick duration (presets + custom)
- [ ] Weekly review auto-sends every Sunday 7pm
- [ ] GCal connected, meeting prep fires 30 min before events
- [ ] `/search` works from Telegram
- [ ] Tasks editable (title/due/priority) from Telegram
- [ ] Web app: all 6 pages functional on desktop + mobile
- [ ] Web app: source tagging visible (`[Gmail]` / `[NUS Outlook]`)
- [ ] 2 Gmail accounts polled independently when connected
