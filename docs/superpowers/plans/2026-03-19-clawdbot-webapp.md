# Clawdbot Web App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js 15 web app (dark minimal design) as a full alternative interaction surface to Telegram — tasks, inbox, digest, replies, search, focus.

**Architecture:** Next.js 15 App Router frontend hitting the existing FastAPI REST backend at localhost:8000. SWR for client-side data fetching. shadcn/ui + Tailwind for components. The FastAPI backend is unchanged; only the frontend changes (replacing Jinja2 templates).

**Tech Stack:** Next.js 15 (App Router), TypeScript, shadcn/ui, Tailwind CSS, SWR, Geist font

---

## Context

- **Design spec:** `docs/superpowers/specs/2026-03-19-clawdbot-phase4-design.md`
- **Existing API routes:** `apps/api/src/api/routes/dashboard_api.py`
- **ORM models:** `packages/core/src/core/db/models.py`
- **Docker Compose:** `infra/docker-compose.yml`
- **FastAPI entry:** `apps/api/src/api/main.py` — router mounted at `/api` prefix

## Existing FastAPI endpoints (already live at port 8000)

```
GET  /api/tasks                  — ActionItems for default_user (status=proposed, ordered by priority desc)
POST /api/tasks/{id}/accept      — Sets status="active"
POST /api/tasks/{id}/dismiss     — Sets status="dismissed"
GET  /api/messages               — Last 20 messages with summary_short + urgency
GET  /api/pvi/today              — {score, regime, explanation, date} or nulls if no row yet
GET  /health                     — {status: "ok"}
```

## New FastAPI endpoints needed (Task 9)

```
GET  /api/replies                — ReplyDraft JOIN Message filter by user_id, status="proposed"
POST /api/replies/{id}/send      — Mark sent, trigger Gmail send
POST /api/replies/{id}/dismiss   — Mark dismissed
POST /api/replies/{id}/update    — Body: {draft_text: str}, update draft_text in place
GET  /api/digest/today           — Digest row for today; if missing, call generate_digest() on-demand
GET  /api/digest/weekly          — Most recent weekly Digest row (regime="weekly")
POST /api/digest/generate        — Regenerate today's digest
GET  /api/focus/status           — Active FocusSession for user (is_active=True)
POST /api/focus/start            — Body: {duration_minutes: int}; ends_at = started_at + timedelta(minutes=duration_minutes)
POST /api/focus/end              — Set is_active=False, ended_early_at=now()
GET  /api/search?q=<query>       — ILIKE on ActionItem.title + Message.title + Message.sender
GET  /api/pvi/history?days=7     — [{date, score, regime}] for last N days from pvi_daily_scores
GET  /api/sources                — All Source rows for default_user (for dynamic inbox filter tabs)
GET  /api/messages?source_id=X   — Messages filtered by source_id (extend existing endpoint)
```

## Key ORM model shapes (for implementer reference)

```python
# ReplyDraft — no user_id column; join via message_id → Message.user_id
ReplyDraft: id, message_id, tone, draft_text, status ("proposed"|"sent"|"dismissed"), created_at

# FocusSession — ends_at already exists, no migration needed
FocusSession: id, user_id, started_at, ends_at, ended_early_at, is_active

# Digest: id, user_id, date, content_md, regime, generated_at
# PVIDailyScore: id, user_id, date, score, regime, explanation, computed_at
# Source: id, user_id, source_type, display_name, config_json, last_synced_at, sync_cursor
```

---

## Task 1: Project scaffold

**Scope:** Bootstrap `apps/web/`, install all dependencies, configure design tokens, create typed API layer and SWR hooks.

### Steps

- [ ] 1.1 Scaffold Next.js app

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  pnpm dlx create-next-app@latest apps/web \
    --typescript \
    --tailwind \
    --app \
    --no-src-dir \
    --import-alias "@/*" \
    --no-eslint
  ```

  Accept all prompts with defaults. This creates `apps/web/` with App Router layout.

- [ ] 1.2 Install runtime dependencies

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  pnpm add swr geist recharts
  pnpm add -D @types/node
  ```

- [ ] 1.3 Install and initialise shadcn/ui

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  pnpm dlx shadcn@latest init
  ```

  When prompted:
  - Style: **Default**
  - Base colour: **Zinc**
  - CSS variables: **yes**

  Then add the specific components used across the app:

  ```bash
  pnpm dlx shadcn@latest add button badge checkbox drawer input tabs
  ```

- [ ] 1.4 Configure design tokens in `apps/web/tailwind.config.ts`

  Extend the default Tailwind config with Clawdbot's exact colour palette. The file must contain:

  ```ts
  import type { Config } from "tailwindcss";

  const config: Config = {
    darkMode: "class",
    content: [
      "./app/**/*.{ts,tsx}",
      "./components/**/*.{ts,tsx}",
      "./lib/**/*.{ts,tsx}",
    ],
    theme: {
      extend: {
        colors: {
          bg: "#0f1117",
          sidebar: "#13151f",
          card: "#1a1d27",
          border: "rgba(255,255,255,0.06)",
          accent: "#7c3aed",
          "accent-light": "#a78bfa",
          text: "#e2e8f0",
          muted: "#6c7086",
          urgent: "#f87171",
          medium: "#fbbf24",
          done: "#34d399",
        },
        fontFamily: {
          sans: ["var(--font-geist-sans)", "sans-serif"],
          mono: ["var(--font-geist-mono)", "monospace"],
        },
        boxShadow: {
          "glow-accent": "0 0 8px rgba(124, 58, 237, 0.15)",
          "glow-done": "0 0 8px rgba(52, 211, 153, 0.15)",
        },
      },
    },
    plugins: [],
  };

  export default config;
  ```

- [ ] 1.5 Update `apps/web/app/globals.css`

  Replace the generated CSS with:

  ```css
  @tailwind base;
  @tailwind components;
  @tailwind utilities;

  :root {
    --font-geist-sans: "Geist", sans-serif;
    --font-geist-mono: "Geist Mono", monospace;
  }

  body {
    background-color: #0f1117;
    color: #e2e8f0;
    font-family: var(--font-geist-sans);
  }

  /* Custom scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: #13151f; }
  ::-webkit-scrollbar-thumb { background: rgba(124, 58, 237, 0.4); border-radius: 2px; }
  ```

- [ ] 1.6 Create `apps/web/lib/api.ts`

  Full typed fetch wrapper. All requests send `X-API-Key: <key>` header (reads from `process.env.NEXT_PUBLIC_API_KEY`). Base URL defaults to `http://localhost:8000`.

  ```ts
  // apps/web/lib/api.ts

  const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

  function headers(): HeadersInit {
    return API_KEY ? { "X-API-Key": API_KEY } : {};
  }

  async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...headers(), ...(init?.headers ?? {}) },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
    return res.json() as Promise<T>;
  }

  // --- Types ---

  export interface Task {
    id: string;
    title: string;
    details: string;
    due_at: string | null;
    priority: number;
    status: "proposed" | "active" | "done" | "dismissed" | "snoozed";
    source_display_name?: string;
  }

  export interface Message {
    id: string;
    sender: string;
    title: string;
    body_preview: string;
    message_ts: string;
    summary_short: string | null;
    urgency: number | null;
    source_display_name?: string;
    source_id?: string;
  }

  export interface PVIToday {
    score: number | null;
    regime: string | null;
    explanation: string | null;
    date?: string;
  }

  export interface PVIHistoryPoint {
    date: string;
    score: number;
    regime: string;
  }

  export interface ReplyDraft {
    id: string;
    message_id: string;
    tone: string;
    draft_text: string;
    status: "proposed" | "sent" | "dismissed";
    created_at: string;
    sender?: string;
    subject?: string;
  }

  export interface DigestToday {
    date: string;
    content_md: string;
    regime: string;
    generated_at: string;
  }

  export interface FocusStatus {
    is_active: boolean;
    started_at: string | null;
    ends_at: string | null;
    session_id: string | null;
  }

  export interface SearchResults {
    tasks: Task[];
    messages: Message[];
  }

  export interface Source {
    id: string;
    source_type: string;
    display_name: string;
    last_synced_at: string | null;
  }

  // --- Fetchers (used by SWR hooks) ---

  export const fetchers = {
    tasks: () => apiFetch<Task[]>("/api/tasks"),
    messages: (sourceId?: string) =>
      apiFetch<Message[]>(sourceId ? `/api/messages?source_id=${sourceId}` : "/api/messages"),
    pviToday: () => apiFetch<PVIToday>("/api/pvi/today"),
    pviHistory: (days = 7) => apiFetch<PVIHistoryPoint[]>(`/api/pvi/history?days=${days}`),
    replies: () => apiFetch<ReplyDraft[]>("/api/replies"),
    digestToday: () => apiFetch<DigestToday>("/api/digest/today"),
    digestWeekly: () => apiFetch<DigestToday>("/api/digest/weekly"),
    focusStatus: () => apiFetch<FocusStatus>("/api/focus/status"),
    sources: () => apiFetch<Source[]>("/api/sources"),
    search: (q: string) => apiFetch<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`),
  };

  // --- Mutations ---

  export const api = {
    acceptTask: (id: string) => apiFetch(`/api/tasks/${id}/accept`, { method: "POST" }),
    dismissTask: (id: string) => apiFetch(`/api/tasks/${id}/dismiss`, { method: "POST" }),
    sendReply: (id: string) => apiFetch(`/api/replies/${id}/send`, { method: "POST" }),
    dismissReply: (id: string) => apiFetch(`/api/replies/${id}/dismiss`, { method: "POST" }),
    updateReply: (id: string, draft_text: string) =>
      apiFetch(`/api/replies/${id}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_text }),
      }),
    generateDigest: () => apiFetch("/api/digest/generate", { method: "POST" }),
    startFocus: (duration_minutes: number) =>
      apiFetch("/api/focus/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_minutes }),
      }),
    endFocus: () => apiFetch("/api/focus/end", { method: "POST" }),
  };
  ```

- [ ] 1.7 Create `apps/web/lib/swr-hooks.ts`

  ```ts
  // apps/web/lib/swr-hooks.ts
  import useSWR from "swr";
  import { fetchers } from "./api";
  import type { Task, Message, PVIToday, PVIHistoryPoint, ReplyDraft, DigestToday, FocusStatus, Source } from "./api";

  // Re-export types for convenience in pages/components
  export type { Task, Message, PVIToday, PVIHistoryPoint, ReplyDraft, DigestToday, FocusStatus, Source };

  export function useTasks() {
    return useSWR<Task[]>("tasks", fetchers.tasks, { refreshInterval: 30_000 });
  }

  export function useMessages(sourceId?: string) {
    const key = sourceId ? `messages-${sourceId}` : "messages";
    return useSWR<Message[]>(key, () => fetchers.messages(sourceId), { refreshInterval: 30_000 });
  }

  export function usePVI() {
    return useSWR<PVIToday>("pvi-today", fetchers.pviToday, { refreshInterval: 60_000 });
  }

  export function usePVIHistory(days = 7) {
    return useSWR<PVIHistoryPoint[]>(`pvi-history-${days}`, () => fetchers.pviHistory(days), {
      refreshInterval: 300_000,
    });
  }

  export function useReplies() {
    return useSWR<ReplyDraft[]>("replies", fetchers.replies, { refreshInterval: 30_000 });
  }

  export function useDigest() {
    return useSWR<DigestToday>("digest-today", fetchers.digestToday, { refreshInterval: 120_000 });
  }

  export function useDigestWeekly() {
    return useSWR<DigestToday>("digest-weekly", fetchers.digestWeekly, { refreshInterval: 300_000 });
  }

  export function useFocus() {
    return useSWR<FocusStatus>("focus-status", fetchers.focusStatus, { refreshInterval: 5_000 });
  }

  export function useSources() {
    return useSWR<Source[]>("sources", fetchers.sources, { refreshInterval: 300_000 });
  }
  ```

- [ ] 1.8 Create `.env.local` for local dev

  Create `apps/web/.env.local`:

  ```
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
  NEXT_PUBLIC_API_KEY=
  ```

  `NEXT_PUBLIC_API_KEY` stays empty if `DASHBOARD_API_KEY` is unset in the FastAPI backend (auth disabled).

- [ ] 1.9 Verify scaffold builds

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  pnpm build
  ```

  Expected: build succeeds with 0 type errors. The only pages at this point are the default Next.js placeholders.

- [ ] 1.10 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): scaffold Next.js 15 app with design tokens and API layer"
  ```

---

## Task 2: Layout + Sidebar

**Scope:** Root layout, sidebar, bottom nav, top bar, reusable status chip.

**Files created:**
- `apps/web/components/layout/Sidebar.tsx`
- `apps/web/components/layout/BottomNav.tsx`
- `apps/web/components/layout/TopBar.tsx`
- `apps/web/components/shared/StatusChip.tsx`
- `apps/web/app/layout.tsx` (replace generated)
- `apps/web/app/page.tsx` (redirect to /tasks)

### Steps

- [ ] 2.1 Create `apps/web/components/shared/StatusChip.tsx`

  Reusable glow chip. Props: `label: string`, `value: string | number | null`, `color: "accent" | "done"`.

  ```tsx
  // apps/web/components/shared/StatusChip.tsx
  "use client";

  interface Props {
    label: string;
    value: string | number | null;
    color?: "accent" | "done";
  }

  export function StatusChip({ label, value, color = "accent" }: Props) {
    const glowClass = color === "done" ? "shadow-glow-done" : "shadow-glow-accent";
    const ringColor = color === "done" ? "border-done" : "border-accent";
    return (
      <div
        className={`inline-flex items-center gap-1.5 rounded-full border ${ringColor} bg-card px-3 py-1 text-xs font-mono ${glowClass}`}
      >
        <span className="text-muted">{label}</span>
        <span className={color === "done" ? "text-done" : "text-accent-light"}>
          {value ?? "—"}
        </span>
      </div>
    );
  }
  ```

- [ ] 2.2 Create `apps/web/components/layout/Sidebar.tsx`

  Desktop-only (hidden on mobile). 48px wide icon column, slides out 160px pill tooltip on hover using pure CSS (`:hover` sibling combinator — no JS).

  Nav items: Tasks (`/tasks`), Inbox (`/inbox`), Digest (`/digest`), Replies (`/replies`), Search (`/search`), Focus (`/focus`).

  Active state: icon bg `#1e2130`, icon colour `text-accent-light`. Use `usePathname()` from `next/navigation`.

  ```tsx
  // apps/web/components/layout/Sidebar.tsx
  "use client";
  import Link from "next/link";
  import { usePathname } from "next/navigation";

  const NAV = [
    { href: "/tasks",   icon: "✓",  label: "Tasks"   },
    { href: "/inbox",   icon: "✉",  label: "Inbox"   },
    { href: "/digest",  icon: "◈",  label: "Digest"  },
    { href: "/replies", icon: "↩",  label: "Replies" },
    { href: "/search",  icon: "⌕",  label: "Search"  },
    { href: "/focus",   icon: "◎",  label: "Focus"   },
  ];

  export function Sidebar() {
    const pathname = usePathname();
    return (
      <nav
        className="hidden md:flex flex-col items-center w-12 min-h-screen bg-sidebar border-r border-border py-4 gap-1 z-20 shrink-0"
        aria-label="Main navigation"
      >
        {NAV.map(({ href, icon, label }) => {
          const active = pathname === href;
          return (
            <div key={href} className="relative group w-full flex justify-center">
              <Link
                href={href}
                className={`flex items-center justify-center w-9 h-9 rounded-lg text-lg transition-colors
                  ${active
                    ? "bg-[#1e2130] text-accent-light"
                    : "text-muted hover:text-text hover:bg-[#1a1d27]"
                  }`}
                aria-current={active ? "page" : undefined}
              >
                {icon}
              </Link>
              {/* CSS-only tooltip — no JS, no library */}
              <span
                className="pointer-events-none absolute left-11 top-1/2 -translate-y-1/2
                  bg-[#1e2130] text-accent-light text-xs font-sans px-3 py-1.5 rounded-full
                  border border-accent/20 whitespace-nowrap
                  opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50"
              >
                {label}
              </span>
            </div>
          );
        })}
      </nav>
    );
  }
  ```

- [ ] 2.3 Create `apps/web/components/layout/BottomNav.tsx`

  Mobile-only (shown below `md` breakpoint). Fixed bottom bar with icon + label for all 6 pages.

  ```tsx
  // apps/web/components/layout/BottomNav.tsx
  "use client";
  import Link from "next/link";
  import { usePathname } from "next/navigation";

  const NAV = [
    { href: "/tasks",   icon: "✓", label: "Tasks"   },
    { href: "/inbox",   icon: "✉", label: "Inbox"   },
    { href: "/digest",  icon: "◈", label: "Digest"  },
    { href: "/replies", icon: "↩", label: "Replies" },
    { href: "/focus",   icon: "◎", label: "Focus"   },
  ];

  export function BottomNav() {
    const pathname = usePathname();
    return (
      <nav
        className="md:hidden fixed bottom-0 inset-x-0 bg-sidebar border-t border-border
          flex justify-around items-center h-16 z-30"
        aria-label="Mobile navigation"
      >
        {NAV.map(({ href, icon, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center gap-0.5 text-xs transition-colors
                ${active ? "text-accent-light" : "text-muted"}`}
              aria-current={active ? "page" : undefined}
            >
              <span className="text-base">{icon}</span>
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    );
  }
  ```

- [ ] 2.4 Create `apps/web/components/layout/TopBar.tsx`

  Shows PVI chip and Worker chip (using `StatusChip`). On mobile, also shows search icon that links to `/search`. Fetches live PVI + focus data via SWR.

  ```tsx
  // apps/web/components/layout/TopBar.tsx
  "use client";
  import Link from "next/link";
  import { StatusChip } from "@/components/shared/StatusChip";
  import { usePVI, useFocus } from "@/lib/swr-hooks";

  export function TopBar() {
    const { data: pvi } = usePVI();
    const { data: focus } = useFocus();

    return (
      <header className="flex items-center justify-between h-12 px-4 border-b border-border bg-sidebar shrink-0">
        <span className="text-sm font-mono text-muted">clawdbot</span>
        <div className="flex items-center gap-2">
          {pvi?.score != null && (
            <StatusChip label="PVI" value={`${pvi.score} · ${pvi.regime}`} color="accent" />
          )}
          {focus?.is_active && (
            <StatusChip label="Worker" value="Focus" color="done" />
          )}
          {!focus?.is_active && (
            <StatusChip label="Worker" value="Active" color="done" />
          )}
          {/* Mobile search icon */}
          <Link href="/search" className="md:hidden text-muted hover:text-text ml-2 text-lg">
            ⌕
          </Link>
        </div>
      </header>
    );
  }
  ```

- [ ] 2.5 Replace `apps/web/app/layout.tsx`

  Wire Sidebar + BottomNav + TopBar into root layout. Apply `dark` class to `<html>`. Load Geist fonts via `next/font/google`.

  ```tsx
  // apps/web/app/layout.tsx
  import type { Metadata } from "next";
  import { GeistSans } from "geist/font/sans";
  import { GeistMono } from "geist/font/mono";
  import { Sidebar } from "@/components/layout/Sidebar";
  import { BottomNav } from "@/components/layout/BottomNav";
  import { TopBar } from "@/components/layout/TopBar";
  import "./globals.css";

  export const metadata: Metadata = {
    title: "Clawdbot",
    description: "Personal ops dashboard",
  };

  export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
      <html lang="en" className="dark">
        <body className={`${GeistSans.variable} ${GeistMono.variable} bg-bg text-text`}>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
              <TopBar />
              <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
                {children}
              </main>
            </div>
          </div>
          <BottomNav />
        </body>
      </html>
    );
  }
  ```

  Note: `pb-16 md:pb-0` prevents bottom nav from overlapping content on mobile.

- [ ] 2.6 Create `apps/web/app/page.tsx` (redirect to /tasks)

  ```tsx
  // apps/web/app/page.tsx
  import { redirect } from "next/navigation";
  export default function Home() {
    redirect("/tasks");
  }
  ```

- [ ] 2.7 Manual verification

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  pnpm dev
  ```

  Open `http://localhost:3000`. Verify:
  - Redirects to `/tasks`
  - Left sidebar visible on desktop, hidden on mobile
  - Bottom nav visible on mobile viewport (<768px)
  - Hovering a sidebar icon shows pill tooltip (pure CSS, no JS flicker)
  - Active page icon has purple highlight
  - TopBar shows "clawdbot" label + placeholder chips

- [ ] 2.8 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add layout shell — sidebar, bottom nav, top bar"
  ```

---

## Task 3: /tasks page

**Scope:** Task list with filter tabs, task rows, priority/source badges, snooze picker, new task drawer, stat bar.

**Files created:**
- `apps/web/components/shared/PriorityBadge.tsx`
- `apps/web/components/shared/SourceBadge.tsx`
- `apps/web/components/tasks/TaskRow.tsx`
- `apps/web/components/tasks/SnoozePicker.tsx`
- `apps/web/components/tasks/NewTaskDrawer.tsx`
- `apps/web/app/tasks/page.tsx`

### Steps

- [ ] 3.1 Create `apps/web/components/shared/PriorityBadge.tsx`

  Maps numeric priority to colour + emoji. Thresholds: >=70 → urgent (red 🔴), >=40 → medium (amber 🟡), else → low (green 🟢).

  ```tsx
  // apps/web/components/shared/PriorityBadge.tsx
  interface Props { priority: number; }

  export function PriorityBadge({ priority }: Props) {
    let emoji = "🟢";
    let cls = "text-done bg-done/10";
    let label = "Low";
    if (priority >= 70) { emoji = "🔴"; cls = "text-urgent bg-urgent/10"; label = "High"; }
    else if (priority >= 40) { emoji = "🟡"; cls = "text-medium bg-medium/10"; label = "Med"; }
    return (
      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-mono ${cls}`}>
        {emoji} {label}
      </span>
    );
  }
  ```

- [ ] 3.2 Create `apps/web/components/shared/SourceBadge.tsx`

  Shows `[Gmail]`, `[NUS Outlook]`, etc. based on the `display_name` string from the Source.

  ```tsx
  // apps/web/components/shared/SourceBadge.tsx
  interface Props { name?: string; }

  export function SourceBadge({ name }: Props) {
    if (!name) return null;
    return (
      <span className="inline-flex text-xs px-2 py-0.5 rounded border border-border text-muted font-mono">
        [{name}]
      </span>
    );
  }
  ```

- [ ] 3.3 Create `apps/web/components/tasks/SnoozePicker.tsx`

  Dropdown with preset options. On selection, calls `onSnooze(isoString)`. Custom option shows a `<input type="datetime-local">`.

  ```tsx
  // apps/web/components/tasks/SnoozePicker.tsx
  "use client";
  import { useState } from "react";
  import { addHours, startOfTomorrow, addDays } from "date-fns";

  interface Props {
    onSnooze: (until: string) => void;
    onClose: () => void;
  }

  export function SnoozePicker({ onSnooze, onClose }: Props) {
    const [custom, setCustom] = useState("");
    const presets = [
      { label: "1 hour",          value: () => addHours(new Date(), 1).toISOString() },
      { label: "3 hours",         value: () => addHours(new Date(), 3).toISOString() },
      { label: "Tomorrow morning",value: () => { const d = startOfTomorrow(); d.setHours(8); return d.toISOString(); } },
    ];
    return (
      <div className="absolute right-0 top-8 z-50 bg-card border border-border rounded-lg shadow-lg p-2 w-48 text-sm">
        {presets.map(p => (
          <button
            key={p.label}
            onClick={() => { onSnooze(p.value()); onClose(); }}
            className="w-full text-left px-3 py-2 rounded hover:bg-[#1e2130] text-text"
          >
            {p.label}
          </button>
        ))}
        <hr className="border-border my-1" />
        <div className="px-2 py-1">
          <input
            type="datetime-local"
            value={custom}
            onChange={e => setCustom(e.target.value)}
            className="w-full bg-bg border border-border rounded px-2 py-1 text-xs text-text"
          />
          {custom && (
            <button
              onClick={() => { onSnooze(new Date(custom).toISOString()); onClose(); }}
              className="mt-1 w-full text-center text-accent-light text-xs hover:underline"
            >
              Confirm
            </button>
          )}
        </div>
      </div>
    );
  }
  ```

  Note: `date-fns` is a transitive dep of shadcn/ui — no separate install needed. If missing: `pnpm add date-fns`.

- [ ] 3.4 Create `apps/web/components/tasks/TaskRow.tsx`

  Renders a single task. Props: `task: Task`, `onAccept`, `onDismiss`, `onSnooze`. Checkbox border colour maps to priority (urgent/medium/done CSS colours). Proposed tasks show Accept + Dismiss inline; done tasks get strikethrough + 45% opacity.

  ```tsx
  // apps/web/components/tasks/TaskRow.tsx
  "use client";
  import { useState } from "react";
  import type { Task } from "@/lib/api";
  import { PriorityBadge } from "@/components/shared/PriorityBadge";
  import { SourceBadge } from "@/components/shared/SourceBadge";
  import { SnoozePicker } from "./SnoozePicker";

  interface Props {
    task: Task;
    onAccept: (id: string) => void;
    onDismiss: (id: string) => void;
    onSnooze: (id: string, until: string) => void;
  }

  function checkboxColor(priority: number) {
    if (priority >= 70) return "border-urgent";
    if (priority >= 40) return "border-medium";
    return "border-done";
  }

  export function TaskRow({ task, onAccept, onDismiss, onSnooze }: Props) {
    const [showSnooze, setShowSnooze] = useState(false);
    const [showMenu, setShowMenu] = useState(false);
    const isDone = task.status === "done";
    const isProposed = task.status === "proposed";

    return (
      <div
        className={`flex items-start gap-3 px-4 py-3 border-b border-border
          ${isDone ? "opacity-45" : isProposed ? "opacity-70" : "opacity-100"}`}
      >
        {/* Checkbox */}
        <div
          className={`mt-0.5 w-4 h-4 shrink-0 rounded border-2 ${checkboxColor(task.priority)}
            ${isDone ? "bg-done/20" : "bg-transparent"} cursor-pointer`}
          onClick={() => !isDone && onAccept(task.id)}
          role="checkbox"
          aria-checked={isDone}
          tabIndex={0}
        />

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className={`text-sm text-text truncate ${isDone ? "line-through" : ""}`}>
            {task.title}
          </p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <SourceBadge name={task.source_display_name} />
            <PriorityBadge priority={task.priority} />
            {task.due_at && (
              <span className="text-xs text-muted font-mono">
                {new Date(task.due_at).toLocaleDateString()}
              </span>
            )}
          </div>

          {/* Proposed actions */}
          {isProposed && (
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => onAccept(task.id)}
                className="text-xs px-3 py-1 rounded bg-accent/20 text-accent-light hover:bg-accent/30"
              >
                Accept
              </button>
              <button
                onClick={() => onDismiss(task.id)}
                className="text-xs px-3 py-1 rounded bg-border/50 text-muted hover:bg-border"
              >
                Dismiss
              </button>
            </div>
          )}
        </div>

        {/* Context menu */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(v => !v)}
            className="text-muted hover:text-text text-lg leading-none px-1"
            aria-label="Task actions"
          >
            ···
          </button>
          {showMenu && (
            <div className="absolute right-0 top-6 z-50 bg-card border border-border rounded-lg shadow-lg p-1 w-36 text-sm">
              <button
                className="w-full text-left px-3 py-2 rounded hover:bg-[#1e2130] text-text"
                onClick={() => { setShowMenu(false); setShowSnooze(true); }}
              >
                Snooze
              </button>
              <button
                className="w-full text-left px-3 py-2 rounded hover:bg-[#1e2130] text-urgent"
                onClick={() => { setShowMenu(false); onDismiss(task.id); }}
              >
                Dismiss
              </button>
            </div>
          )}
          {showSnooze && (
            <SnoozePicker
              onSnooze={until => onSnooze(task.id, until)}
              onClose={() => setShowSnooze(false)}
            />
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] 3.5 Create `apps/web/components/tasks/NewTaskDrawer.tsx`

  Slide-in drawer (shadcn `Drawer`) with title, due date, priority (Low/Med/High) fields. On submit: `POST /api/tasks` (note: this endpoint does not exist yet — see note below). Until the endpoint exists, the button is disabled with a tooltip "Manual tasks coming soon".

  Note: `POST /api/tasks` (create task) is NOT in scope for Task 9. If it becomes needed, it is a straightforward addition to `dashboard_api.py`. For now the drawer exists but submit posts to a no-op.

  ```tsx
  // apps/web/components/tasks/NewTaskDrawer.tsx
  "use client";
  import { useState } from "react";
  import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer";
  import { Button } from "@/components/ui/button";

  export function NewTaskDrawer() {
    const [title, setTitle] = useState("");
    const [due, setDue] = useState("");
    const [priority, setPriority] = useState("50");

    return (
      <Drawer>
        <DrawerTrigger asChild>
          <Button variant="outline" size="sm" className="border-accent text-accent-light hover:bg-accent/10">
            + New task
          </Button>
        </DrawerTrigger>
        <DrawerContent className="bg-card border-t border-border p-6">
          <DrawerHeader>
            <DrawerTitle className="text-text">New Task</DrawerTitle>
          </DrawerHeader>
          <div className="flex flex-col gap-4 mt-4">
            <input
              placeholder="Task title"
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="bg-bg border border-border rounded px-3 py-2 text-text text-sm outline-none focus:border-accent"
            />
            <input
              type="datetime-local"
              value={due}
              onChange={e => setDue(e.target.value)}
              className="bg-bg border border-border rounded px-3 py-2 text-text text-sm outline-none focus:border-accent"
            />
            <select
              value={priority}
              onChange={e => setPriority(e.target.value)}
              className="bg-bg border border-border rounded px-3 py-2 text-text text-sm outline-none focus:border-accent"
            >
              <option value="30">Low</option>
              <option value="50">Medium</option>
              <option value="80">High</option>
            </select>
            <Button disabled className="mt-2 opacity-40 cursor-not-allowed" title="Manual task creation coming soon">
              Save task
            </Button>
          </div>
        </DrawerContent>
      </Drawer>
    );
  }
  ```

- [ ] 3.6 Create `apps/web/app/tasks/page.tsx`

  Filter tabs (All / Today / Overdue / Proposed). Bottom stat bar. Calls `useTasks()` for data. Client-side filtering — one SWR call, filter locally.

  ```tsx
  // apps/web/app/tasks/page.tsx
  "use client";
  import { useState } from "react";
  import { useTasks } from "@/lib/swr-hooks";
  import { api } from "@/lib/api";
  import type { Task } from "@/lib/api";
  import { TaskRow } from "@/components/tasks/TaskRow";
  import { NewTaskDrawer } from "@/components/tasks/NewTaskDrawer";

  type Filter = "all" | "today" | "overdue" | "proposed";

  function filterTasks(tasks: Task[], filter: Filter): Task[] {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    return tasks.filter(t => {
      if (filter === "proposed") return t.status === "proposed";
      if (filter === "all") return !["done", "dismissed"].includes(t.status);
      const due = t.due_at ? new Date(t.due_at) : null;
      if (filter === "today") return due && due >= today && due < tomorrow;
      if (filter === "overdue") return due && due < today && !["done", "dismissed"].includes(t.status);
      return true;
    });
  }

  export default function TasksPage() {
    const { data: tasks = [], mutate } = useTasks();
    const [filter, setFilter] = useState<Filter>("all");

    const handleAccept = async (id: string) => {
      await api.acceptTask(id);
      mutate();
    };
    const handleDismiss = async (id: string) => {
      await api.dismissTask(id);
      mutate();
    };
    const handleSnooze = async (_id: string, _until: string) => {
      // Snooze endpoint not yet in scope — show toast when implemented
    };

    const filtered = filterTasks(tasks, filter);
    const active = tasks.filter(t => t.status === "active").length;
    const overdue = tasks.filter(t => {
      const due = t.due_at ? new Date(t.due_at) : null;
      return due && due < new Date() && !["done", "dismissed"].includes(t.status);
    }).length;
    const proposed = tasks.filter(t => t.status === "proposed").length;
    const doneToday = tasks.filter(t => {
      if (t.status !== "done") return false;
      const u = t.due_at ? new Date(t.due_at) : null;
      return u && u.toDateString() === new Date().toDateString();
    }).length;

    const TABS: { label: string; value: Filter }[] = [
      { label: "All", value: "all" },
      { label: "Today", value: "today" },
      { label: "Overdue", value: "overdue" },
      { label: "Proposed", value: "proposed" },
    ];

    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-text">Tasks</h1>
          <NewTaskDrawer />
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 px-4 pt-3 pb-1">
          {TABS.map(tab => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={`px-3 py-1 rounded-full text-xs font-mono transition-colors
                ${filter === tab.value
                  ? "bg-accent text-white"
                  : "text-muted hover:text-text hover:bg-card"}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Task list */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-muted text-sm text-center mt-12">No tasks in this filter.</p>
          ) : (
            filtered.map(task => (
              <TaskRow
                key={task.id}
                task={task}
                onAccept={handleAccept}
                onDismiss={handleDismiss}
                onSnooze={handleSnooze}
              />
            ))
          )}
        </div>

        {/* Stat bar */}
        <div className="flex gap-4 px-4 py-2 border-t border-border text-xs text-muted font-mono">
          <span>{active} active</span>
          <span className="text-urgent">{overdue} overdue</span>
          <span className="text-medium">{proposed} proposed</span>
          <span className="text-done">{doneToday} done today</span>
        </div>
      </div>
    );
  }
  ```

- [ ] 3.7 Manual verification

  With FastAPI running (`PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/api/src uvicorn api.main:app --reload --port 8000`), navigate to `http://localhost:3000/tasks` and verify:
  - Task list renders (or empty state shown)
  - Filter tabs switch visible tasks
  - Accept/Dismiss buttons call the correct API and optimistically update
  - `···` menu appears and "Snooze" opens the SnoozePicker
  - Stat bar counts are correct

- [ ] 3.8 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /tasks page with filter tabs, task rows, snooze picker"
  ```

---

## Task 4: /inbox page

**Scope:** Message list with source filter tabs, expand panel with action items and reply draft link.

**Files created:**
- `apps/web/components/inbox/MessageRow.tsx`
- `apps/web/components/inbox/MessagePanel.tsx`
- `apps/web/app/inbox/page.tsx`

### Steps

- [ ] 4.1 Create `apps/web/components/inbox/MessageRow.tsx`

  Compact row: source badge, sender, subject, summary preview, timestamp, unread dot. Click toggles expanded state (passed via `isExpanded` + `onToggle` props).

  ```tsx
  // apps/web/components/inbox/MessageRow.tsx
  import type { Message } from "@/lib/api";
  import { SourceBadge } from "@/components/shared/SourceBadge";

  interface Props {
    message: Message;
    isExpanded: boolean;
    onToggle: () => void;
  }

  export function MessageRow({ message, isExpanded, onToggle }: Props) {
    const ts = new Date(message.message_ts);
    const timeStr = ts.toLocaleDateString() === new Date().toLocaleDateString()
      ? ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : ts.toLocaleDateString();

    return (
      <div
        className={`flex items-start gap-3 px-4 py-3 border-b border-border cursor-pointer hover:bg-card/50 transition-colors
          ${isExpanded ? "bg-card/50" : ""}`}
        onClick={onToggle}
        role="button"
        tabIndex={0}
      >
        {/* Unread dot */}
        <div className="mt-1.5 w-2 h-2 shrink-0 rounded-full bg-accent-light" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <SourceBadge name={message.source_display_name} />
            <span className="text-xs text-muted font-mono">{message.sender}</span>
          </div>
          <p className="text-sm text-text truncate">{message.title}</p>
          {message.summary_short && (
            <p className="text-xs text-muted mt-0.5 line-clamp-2">{message.summary_short}</p>
          )}
        </div>
        <span className="text-xs text-muted font-mono shrink-0">{timeStr}</span>
      </div>
    );
  }
  ```

- [ ] 4.2 Create `apps/web/components/inbox/MessagePanel.tsx`

  Expanded panel shown below a `MessageRow`. Shows full summary, extracted action items with Accept/Dismiss inline, and a link to the reply draft if one exists.

  ```tsx
  // apps/web/components/inbox/MessagePanel.tsx
  "use client";
  import type { Message } from "@/lib/api";
  import { api } from "@/lib/api";

  interface ActionItemPreview {
    id: string;
    title: string;
    status: string;
  }

  interface Props {
    message: Message;
    // Action items are fetched from the tasks list filtered by message_id
    actionItems?: ActionItemPreview[];
    hasReplyDraft?: boolean;
    replyDraftId?: string;
    onTaskAccept: (id: string) => void;
    onTaskDismiss: (id: string) => void;
  }

  export function MessagePanel({ message, actionItems = [], hasReplyDraft, replyDraftId, onTaskAccept, onTaskDismiss }: Props) {
    return (
      <div className="px-6 py-4 bg-bg border-b border-border text-sm">
        {/* Full summary */}
        {message.summary_short && (
          <p className="text-text mb-3">{message.summary_short}</p>
        )}

        {/* Action items */}
        {actionItems.length > 0 && (
          <div className="mb-3">
            <p className="text-xs text-muted font-mono uppercase mb-2">Action Items</p>
            <div className="flex flex-col gap-1">
              {actionItems.map(item => (
                <div key={item.id} className="flex items-center justify-between gap-2 py-1">
                  <span className="text-text">{item.title}</span>
                  {item.status === "proposed" && (
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => onTaskAccept(item.id)}
                        className="text-xs px-2 py-0.5 rounded bg-accent/20 text-accent-light hover:bg-accent/30"
                      >
                        Accept
                      </button>
                      <button
                        onClick={() => onTaskDismiss(item.id)}
                        className="text-xs px-2 py-0.5 rounded bg-border/50 text-muted hover:bg-border"
                      >
                        Dismiss
                      </button>
                    </div>
                  )}
                  {item.status !== "proposed" && (
                    <span className="text-xs text-done font-mono">{item.status}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Reply draft link */}
        {hasReplyDraft && replyDraftId && (
          <a
            href={`/replies#${replyDraftId}`}
            className="inline-block text-xs text-accent-light underline hover:text-accent"
          >
            View reply draft →
          </a>
        )}
      </div>
    );
  }
  ```

- [ ] 4.3 Create `apps/web/app/inbox/page.tsx`

  Source filter tabs are generated dynamically from `useSources()`. Expanding a row shows the `MessagePanel` inline. Action items are a simplified subset — for now they come from the tasks list filtered where the message context matches (best-effort; full join is in Task 9's `/api/messages` enhancement).

  ```tsx
  // apps/web/app/inbox/page.tsx
  "use client";
  import { useState } from "react";
  import { useMessages, useSources, useTasks } from "@/lib/swr-hooks";
  import { api } from "@/lib/api";
  import { MessageRow } from "@/components/inbox/MessageRow";
  import { MessagePanel } from "@/components/inbox/MessagePanel";

  export default function InboxPage() {
    const { data: messages = [], mutate: mutateMessages } = useMessages();
    const { data: sources = [] } = useSources();
    const { data: tasks = [], mutate: mutateTasks } = useTasks();
    const [activeSource, setActiveSource] = useState<string | null>(null);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const filtered = activeSource
      ? messages.filter(m => m.source_id === activeSource)
      : messages;

    const handleToggle = (id: string) => {
      setExpandedId(prev => (prev === id ? null : id));
    };

    const handleAccept = async (id: string) => {
      await api.acceptTask(id);
      mutateTasks();
    };
    const handleDismiss = async (id: string) => {
      await api.dismissTask(id);
      mutateTasks();
    };

    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-text">Inbox</h1>
        </div>

        {/* Source filter tabs */}
        <div className="flex gap-1 px-4 pt-3 pb-1 overflow-x-auto">
          <button
            onClick={() => setActiveSource(null)}
            className={`px-3 py-1 rounded-full text-xs font-mono shrink-0 transition-colors
              ${activeSource === null ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-card"}`}
          >
            All
          </button>
          {sources.map(src => (
            <button
              key={src.id}
              onClick={() => setActiveSource(src.id)}
              className={`px-3 py-1 rounded-full text-xs font-mono shrink-0 transition-colors
                ${activeSource === src.id ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-card"}`}
            >
              {src.display_name}
            </button>
          ))}
        </div>

        {/* Message list */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-muted text-sm text-center mt-12">No messages.</p>
          ) : (
            filtered.map(msg => (
              <div key={msg.id}>
                <MessageRow
                  message={msg}
                  isExpanded={expandedId === msg.id}
                  onToggle={() => handleToggle(msg.id)}
                />
                {expandedId === msg.id && (
                  <MessagePanel
                    message={msg}
                    actionItems={tasks
                      .filter(t => (t as any).message_id === msg.id)
                      .map(t => ({ id: t.id, title: t.title, status: t.status }))}
                    onTaskAccept={handleAccept}
                    onTaskDismiss={handleDismiss}
                  />
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }
  ```

  Note: `(t as any).message_id` is a workaround until the `GET /api/tasks` response includes `message_id`. Update the `Task` interface in `lib/api.ts` to include `message_id?: string` once Task 9 adds it.

- [ ] 4.4 Manual verification

  Navigate to `http://localhost:3000/inbox`. Verify:
  - Source tabs generate from connected Sources (or empty state)
  - Messages list renders
  - Clicking a row toggles the expand panel
  - Panel shows summary text
  - Source filter tabs actually filter the list

- [ ] 4.5 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /inbox page with source filter tabs and expand panel"
  ```

---

## Task 5: /digest page

**Scope:** PVI card with sparkline, digest sections (Do Today / Upcoming / Updates), regenerate button, weekly tab.

**Files created:**
- `apps/web/components/digest/PVICard.tsx`
- `apps/web/components/digest/DigestSection.tsx`
- `apps/web/app/digest/page.tsx`

### Steps

- [ ] 5.1 Install recharts (if not already installed)

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  pnpm add recharts
  ```

- [ ] 5.2 Create `apps/web/components/digest/PVICard.tsx`

  Shows PVI score, regime label, and a 7-day sparkline using recharts `LineChart`. Fetches `usePVI()` + `usePVIHistory()`.

  ```tsx
  // apps/web/components/digest/PVICard.tsx
  "use client";
  import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";
  import { usePVI, usePVIHistory } from "@/lib/swr-hooks";

  function regimeColour(regime: string | null): string {
    if (!regime) return "#a78bfa";
    const r = regime.toLowerCase();
    if (r.includes("critical") || r.includes("overload")) return "#f87171";
    if (r.includes("high") || r.includes("elevated")) return "#fbbf24";
    return "#34d399";
  }

  export function PVICard() {
    const { data: pvi } = usePVI();
    const { data: history = [] } = usePVIHistory(7);
    const colour = regimeColour(pvi?.regime ?? null);

    return (
      <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted font-mono uppercase">PVI Today</p>
            <p className="text-4xl font-mono font-bold mt-1" style={{ color: colour }}>
              {pvi?.score ?? "—"}
            </p>
            <p className="text-sm text-muted mt-0.5">{pvi?.regime ?? "No data yet"}</p>
          </div>
          {history.length > 1 && (
            <div className="w-32 h-14">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke={colour}
                    strokeWidth={2}
                    dot={false}
                  />
                  <Tooltip
                    contentStyle={{ background: "#1a1d27", border: "none", fontSize: 11 }}
                    labelFormatter={label => `Date: ${label}`}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        {pvi?.explanation && (
          <p className="text-xs text-muted border-t border-border pt-3">{pvi.explanation}</p>
        )}
      </div>
    );
  }
  ```

- [ ] 5.3 Create `apps/web/components/digest/DigestSection.tsx`

  Renders a named section from the digest content. The `content_md` string from the Digest model is Markdown — render it as plain text parsed into sections by looking for `##` headers matching "DO TODAY", "UPCOMING", "UPDATES". Falls back to rendering the full markdown as-is if sections can't be parsed.

  ```tsx
  // apps/web/components/digest/DigestSection.tsx
  "use client";

  interface Props {
    title: string;
    emoji: string;
    items: string[];
  }

  export function DigestSection({ title, emoji, items }: Props) {
    if (items.length === 0) return null;
    return (
      <div className="mb-4">
        <p className="text-xs text-muted font-mono uppercase mb-2">
          {emoji} {title}
        </p>
        <div className="flex flex-col gap-1">
          {items.map((item, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-text py-1 border-b border-border/50">
              <span className="text-muted mt-0.5">·</span>
              <span>{item}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Helper: parse content_md into sections
  export function parseDigestSections(md: string): { doToday: string[]; upcoming: string[]; updates: string[] } {
    const lines = md.split("\n");
    const sections: { doToday: string[]; upcoming: string[]; updates: string[] } = {
      doToday: [], upcoming: [], updates: [],
    };
    let current: keyof typeof sections | null = null;
    for (const line of lines) {
      const lower = line.toLowerCase();
      if (lower.includes("do today") || lower.includes("📌")) { current = "doToday"; continue; }
      if (lower.includes("upcoming") || lower.includes("📅")) { current = "upcoming"; continue; }
      if (lower.includes("update") || lower.includes("🔄")) { current = "updates"; continue; }
      if (line.startsWith("#")) { current = null; continue; }
      const trimmed = line.replace(/^[-*•]\s*/, "").trim();
      if (trimmed && current) sections[current].push(trimmed);
    }
    return sections;
  }
  ```

- [ ] 5.4 Create `apps/web/app/digest/page.tsx`

  Two tabs: Today (PVI card + digest sections + regenerate button) and Weekly (renders weekly content_md as `<pre>`).

  ```tsx
  // apps/web/app/digest/page.tsx
  "use client";
  import { useState } from "react";
  import { useDigest, useDigestWeekly } from "@/lib/swr-hooks";
  import { api } from "@/lib/api";
  import { PVICard } from "@/components/digest/PVICard";
  import { DigestSection, parseDigestSections } from "@/components/digest/DigestSection";

  export default function DigestPage() {
    const [tab, setTab] = useState<"today" | "weekly">("today");
    const { data: today, mutate: mutateToday, isLoading } = useDigest();
    const { data: weekly } = useDigestWeekly();

    const handleRegenerate = async () => {
      await api.generateDigest();
      mutateToday();
    };

    const sections = today ? parseDigestSections(today.content_md) : null;

    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-text">Digest</h1>
          {tab === "today" && (
            <button
              onClick={handleRegenerate}
              className="text-xs px-3 py-1 rounded border border-border text-muted hover:text-accent-light hover:border-accent transition-colors"
            >
              Regenerate
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 pt-3 pb-1">
          {(["today", "weekly"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-full text-xs font-mono transition-colors
                ${tab === t ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-card"}`}
            >
              {t === "today" ? "Today" : "Weekly"}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {tab === "today" && (
            <>
              <PVICard />
              {isLoading && <p className="text-muted text-sm mt-4">Loading digest...</p>}
              {sections && (
                <div className="mt-4">
                  <DigestSection title="Do Today" emoji="📌" items={sections.doToday} />
                  <DigestSection title="Upcoming" emoji="📅" items={sections.upcoming} />
                  <DigestSection title="Updates" emoji="🔄" items={sections.updates} />
                </div>
              )}
              {!isLoading && !today && (
                <p className="text-muted text-sm mt-4">No digest yet. Click Regenerate to create one.</p>
              )}
            </>
          )}

          {tab === "weekly" && (
            <>
              {weekly ? (
                <div>
                  <p className="text-xs text-muted font-mono mb-2">
                    Generated {new Date(weekly.generated_at).toLocaleDateString()}
                  </p>
                  <pre className="text-sm text-text whitespace-pre-wrap font-sans leading-relaxed">
                    {weekly.content_md}
                  </pre>
                </div>
              ) : (
                <p className="text-muted text-sm">No weekly review available yet.</p>
              )}
            </>
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] 5.5 Manual verification

  Navigate to `http://localhost:3000/digest`. Verify:
  - Today tab shows PVI card (or "No data yet" placeholder)
  - Sparkline renders if PVI history exists
  - Digest sections render with correct emoji headers
  - Regenerate button fires POST and refreshes data
  - Weekly tab renders markdown content or placeholder

- [ ] 5.6 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /digest page with PVI card, sparkline, and digest sections"
  ```

---

## Task 6: /replies page

**Scope:** Pending reply drafts, inline edit textarea, Send/Skip actions, Sent history tab.

**Files created:**
- `apps/web/components/replies/ReplyCard.tsx`
- `apps/web/app/replies/page.tsx`

### Steps

- [ ] 6.1 Create `apps/web/components/replies/ReplyCard.tsx`

  Shows sender, subject, tone badge, full draft text. Edit mode: clicking Edit replaces the draft text with a textarea. Save calls `api.updateReply(id, newText)`. Send calls `api.sendReply(id)`. Skip calls `api.dismissReply(id)`.

  ```tsx
  // apps/web/components/replies/ReplyCard.tsx
  "use client";
  import { useState } from "react";
  import type { ReplyDraft } from "@/lib/api";
  import { api } from "@/lib/api";

  interface Props {
    reply: ReplyDraft;
    onMutate: () => void;
  }

  export function ReplyCard({ reply, onMutate }: Props) {
    const [editing, setEditing] = useState(false);
    const [draftText, setDraftText] = useState(reply.draft_text);
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
      setSaving(true);
      await api.updateReply(reply.id, draftText);
      setSaving(false);
      setEditing(false);
      onMutate();
    };

    const handleSend = async () => {
      await api.sendReply(reply.id);
      onMutate();
    };

    const handleSkip = async () => {
      await api.dismissReply(reply.id);
      onMutate();
    };

    return (
      <div id={reply.id} className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-text">{reply.subject ?? "Reply Draft"}</p>
            <p className="text-xs text-muted mt-0.5">To: {reply.sender ?? "Unknown"}</p>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full border border-border text-muted font-mono">
            {reply.tone}
          </span>
        </div>

        {/* Draft text */}
        {editing ? (
          <textarea
            value={draftText}
            onChange={e => setDraftText(e.target.value)}
            rows={6}
            className="w-full bg-bg border border-accent/40 rounded-lg px-3 py-2 text-sm text-text outline-none focus:border-accent resize-y"
          />
        ) : (
          <p className="text-sm text-text whitespace-pre-wrap leading-relaxed">{draftText}</p>
        )}

        {/* Actions */}
        <div className="flex gap-2 flex-wrap">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={saving}
                className="text-xs px-3 py-1.5 rounded bg-accent text-white hover:bg-accent/80 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => { setEditing(false); setDraftText(reply.draft_text); }}
                className="text-xs px-3 py-1.5 rounded border border-border text-muted hover:text-text"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleSend}
                className="text-xs px-3 py-1.5 rounded bg-done/20 text-done hover:bg-done/30"
              >
                Send
              </button>
              <button
                onClick={() => setEditing(true)}
                className="text-xs px-3 py-1.5 rounded border border-border text-muted hover:text-text"
              >
                Edit
              </button>
              <button
                onClick={handleSkip}
                className="text-xs px-3 py-1.5 rounded border border-border text-urgent/70 hover:text-urgent"
              >
                Skip
              </button>
            </>
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] 6.2 Create `apps/web/app/replies/page.tsx`

  Pending tab (status="proposed") and Sent tab (status="sent"). Both filtered client-side from the same `useReplies()` call.

  ```tsx
  // apps/web/app/replies/page.tsx
  "use client";
  import { useState } from "react";
  import { useReplies } from "@/lib/swr-hooks";
  import { ReplyCard } from "@/components/replies/ReplyCard";

  export default function RepliesPage() {
    const { data: replies = [], mutate } = useReplies();
    const [tab, setTab] = useState<"pending" | "sent">("pending");

    const pending = replies.filter(r => r.status === "proposed");
    const sent = replies.filter(r => r.status === "sent");
    const shown = tab === "pending" ? pending : sent;

    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-text">Replies</h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 pt-3 pb-1">
          {(["pending", "sent"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-full text-xs font-mono transition-colors
                ${tab === t ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-card"}`}
            >
              {t === "pending" ? `Pending (${pending.length})` : `Sent (${sent.length})`}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
          {shown.length === 0 ? (
            <p className="text-muted text-sm text-center mt-12">
              {tab === "pending" ? "No pending replies." : "No sent replies."}
            </p>
          ) : (
            shown.map(reply => (
              <ReplyCard key={reply.id} reply={reply} onMutate={mutate} />
            ))
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] 6.3 Manual verification

  Navigate to `http://localhost:3000/replies`. Verify:
  - Pending tab shows reply drafts (or empty state)
  - Clicking Edit switches to textarea with correct draft text
  - Save calls PATCH and reverts to read mode
  - Send/Skip remove the card from pending list
  - Sent tab shows sent history

- [ ] 6.4 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /replies page with inline edit, send, and skip"
  ```

---

## Task 7: /search page

**Scope:** Auto-focused search input, debounced query, task + message results.

**Files created:**
- `apps/web/app/search/page.tsx`

### Steps

- [ ] 7.1 Create `apps/web/app/search/page.tsx`

  Auto-focuses input on mount (`autoFocus`). Debounces input at 300ms using a local `useState` + `useEffect` timer. Calls `fetchers.search(query)` directly (not via SWR) on each debounced change to avoid key collisions. Shows task results using `TaskRow` (read-only: no accept/dismiss) and message results as compact rows.

  Note: `GET /api/search?q=<query>` must be added in Task 9. Until then, the page renders "Search coming soon" if the endpoint returns 404.

  ```tsx
  // apps/web/app/search/page.tsx
  "use client";
  import { useState, useEffect, useCallback } from "react";
  import { fetchers } from "@/lib/api";
  import type { SearchResults } from "@/lib/api";
  import { TaskRow } from "@/components/tasks/TaskRow";
  import { SourceBadge } from "@/components/shared/SourceBadge";

  export default function SearchPage() {
    const [query, setQuery] = useState("");
    const [debouncedQuery, setDebouncedQuery] = useState("");
    const [results, setResults] = useState<SearchResults | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Debounce 300ms
    useEffect(() => {
      const t = setTimeout(() => setDebouncedQuery(query), 300);
      return () => clearTimeout(t);
    }, [query]);

    // Fetch on debounced query change
    useEffect(() => {
      if (!debouncedQuery.trim()) { setResults(null); return; }
      setLoading(true);
      setError(null);
      fetchers.search(debouncedQuery)
        .then(setResults)
        .catch(err => {
          if (err.message?.includes("404")) {
            setError("Search endpoint not yet available. Complete Task 9 first.");
          } else {
            setError("Search failed. Is the API running?");
          }
        })
        .finally(() => setLoading(false));
    }, [debouncedQuery]);

    const noop = () => {};

    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-3 border-b border-border">
          <input
            autoFocus
            placeholder="Search tasks and messages..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-text text-sm outline-none focus:border-accent transition-colors"
          />
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && <p className="text-muted text-sm text-center mt-8">Searching...</p>}
          {error && <p className="text-urgent text-sm text-center mt-8 px-4">{error}</p>}

          {results && !loading && (
            <>
              {/* Task results */}
              {results.tasks.length > 0 && (
                <div>
                  <p className="text-xs text-muted font-mono uppercase px-4 pt-4 pb-2">
                    Tasks ({results.tasks.length})
                  </p>
                  {results.tasks.map(task => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      onAccept={noop}
                      onDismiss={noop}
                      onSnooze={noop}
                    />
                  ))}
                </div>
              )}

              {/* Message results */}
              {results.messages.length > 0 && (
                <div>
                  <p className="text-xs text-muted font-mono uppercase px-4 pt-4 pb-2">
                    Messages ({results.messages.length})
                  </p>
                  {results.messages.map(msg => (
                    <div key={msg.id} className="px-4 py-3 border-b border-border">
                      <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                        <SourceBadge name={msg.source_display_name} />
                        <span className="text-xs text-muted">{msg.sender}</span>
                      </div>
                      <p className="text-sm text-text">{msg.title}</p>
                      {msg.summary_short && (
                        <p className="text-xs text-muted mt-0.5 line-clamp-2">{msg.summary_short}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {results.tasks.length === 0 && results.messages.length === 0 && (
                <p className="text-muted text-sm text-center mt-8">
                  No results for &quot;{debouncedQuery}&quot;
                </p>
              )}
            </>
          )}

          {!query && (
            <p className="text-muted text-sm text-center mt-12">Type to search tasks and messages.</p>
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] 7.2 Manual verification

  Navigate to `http://localhost:3000/search`. Verify:
  - Input auto-focuses on page load
  - Typing shows "Searching..." after 300ms
  - Results render task rows + message rows correctly
  - Empty state shows when no matches
  - "No results for X" when query has no hits

- [ ] 7.3 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /search page with debounced query and task/message results"
  ```

---

## Task 8: /focus page

**Scope:** Focus session toggle, duration picker, countdown timer, PVI card, quick stats.

**Files created:**
- `apps/web/components/focus/CountdownTimer.tsx`
- `apps/web/app/focus/page.tsx`

### Steps

- [ ] 8.1 Create `apps/web/components/focus/CountdownTimer.tsx`

  Renders `HH:MM:SS` countdown based on `ends_at`. Uses `setInterval` to tick every second. Turns red when < 5 minutes remain.

  ```tsx
  // apps/web/components/focus/CountdownTimer.tsx
  "use client";
  import { useEffect, useState } from "react";

  interface Props { endsAt: string; }

  function formatSeconds(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return [h, m, sec].map(v => String(v).padStart(2, "0")).join(":");
  }

  export function CountdownTimer({ endsAt }: Props) {
    const [remaining, setRemaining] = useState(0);

    useEffect(() => {
      const tick = () => {
        const diff = Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000));
        setRemaining(diff);
      };
      tick();
      const id = setInterval(tick, 1000);
      return () => clearInterval(id);
    }, [endsAt]);

    const isWarning = remaining < 300; // < 5 min
    const colour = isWarning ? "text-urgent" : "text-done";

    return (
      <div className={`font-mono text-7xl font-bold tabular-nums ${colour}`}>
        {formatSeconds(remaining)}
      </div>
    );
  }
  ```

- [ ] 8.2 Create `apps/web/app/focus/page.tsx`

  Shows active session countdown OR the start form. Duration options: 25, 45, 90, Custom. Start calls `api.startFocus(minutes)`. End calls `api.endFocus()`.

  ```tsx
  // apps/web/app/focus/page.tsx
  "use client";
  import { useState } from "react";
  import { useFocus, usePVI, useTasks } from "@/lib/swr-hooks";
  import { api } from "@/lib/api";
  import { CountdownTimer } from "@/components/focus/CountdownTimer";
  import { PVICard } from "@/components/digest/PVICard";

  const DURATIONS = [
    { label: "25 min", value: 25 },
    { label: "45 min", value: 45 },
    { label: "90 min", value: 90 },
  ];

  export default function FocusPage() {
    const { data: focus, mutate: mutateFocus } = useFocus();
    const { data: tasks = [] } = useTasks();
    const [selectedDuration, setSelectedDuration] = useState(25);
    const [custom, setCustom] = useState("");

    const handleStart = async () => {
      const mins = custom ? parseInt(custom, 10) : selectedDuration;
      if (!mins || isNaN(mins)) return;
      await api.startFocus(mins);
      mutateFocus();
    };

    const handleEnd = async () => {
      await api.endFocus();
      mutateFocus();
    };

    const doneTasks = tasks.filter(t => t.status === "done").length;
    const activeTasks = tasks.filter(t => t.status === "active").length;

    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-3 border-b border-border">
          <h1 className="text-sm font-semibold text-text">Focus</h1>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col items-center gap-6">
          {focus?.is_active && focus.ends_at ? (
            <>
              <p className="text-muted text-sm">Session active</p>
              <CountdownTimer endsAt={focus.ends_at} />
              <button
                onClick={handleEnd}
                className="px-6 py-3 rounded-xl border border-urgent/40 text-urgent hover:bg-urgent/10 transition-colors"
              >
                End Focus
              </button>
            </>
          ) : (
            <>
              <p className="text-muted text-sm">Choose duration</p>

              {/* Duration presets */}
              <div className="flex gap-2 flex-wrap justify-center">
                {DURATIONS.map(d => (
                  <button
                    key={d.value}
                    onClick={() => { setSelectedDuration(d.value); setCustom(""); }}
                    className={`px-4 py-2 rounded-xl border text-sm transition-colors
                      ${selectedDuration === d.value && !custom
                        ? "border-accent bg-accent/20 text-accent-light"
                        : "border-border text-muted hover:border-accent/40 hover:text-text"}`}
                  >
                    {d.label}
                  </button>
                ))}
                <input
                  type="number"
                  placeholder="Custom"
                  value={custom}
                  onChange={e => setCustom(e.target.value)}
                  className="w-24 px-3 py-2 rounded-xl border border-border bg-bg text-text text-sm outline-none focus:border-accent text-center"
                />
              </div>

              <button
                onClick={handleStart}
                className="px-8 py-3 rounded-xl bg-accent text-white hover:bg-accent/80 transition-colors text-sm font-semibold"
              >
                Start Focus
              </button>
            </>
          )}

          {/* Quick stats */}
          <div className="flex gap-6 text-sm font-mono text-muted mt-2">
            <div className="text-center">
              <p className="text-2xl text-done font-bold">{doneTasks}</p>
              <p className="text-xs mt-0.5">Done today</p>
            </div>
            <div className="text-center">
              <p className="text-2xl text-accent-light font-bold">{activeTasks}</p>
              <p className="text-xs mt-0.5">Active</p>
            </div>
          </div>

          <div className="w-full max-w-sm">
            <PVICard />
          </div>
        </div>
      </div>
    );
  }
  ```

- [ ] 8.3 Manual verification

  Navigate to `http://localhost:3000/focus`. Verify:
  - Duration buttons highlight correctly
  - Custom input overrides preset selection
  - Start Focus calls API and switches to countdown view
  - Countdown ticks every second
  - Turns red when < 5 minutes remain
  - End Focus returns to start view
  - Quick stats show correct counts

- [ ] 8.4 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/
  git commit -m "feat(web): add /focus page with countdown timer and session control"
  ```

---

## Task 9: New FastAPI endpoints

**Scope:** Add all endpoints required by the web app to `apps/api/src/api/routes/dashboard_api.py`.

**Files modified:**
- `apps/api/src/api/routes/dashboard_api.py`

### Steps

- [ ] 9.1 Add `GET /api/sources`

  Returns all `Source` rows for `default_user_id`.

  ```python
  @router.get("/sources")
  def get_sources() -> list[dict[str, Any]]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import Source
      settings = get_settings()
      with get_db() as db:
          rows = (
              db.query(Source)
              .filter(Source.user_id == settings.default_user_id)
              .order_by(Source.created_at)
              .all()
          )
          return [
              {
                  "id": str(r.id),
                  "source_type": r.source_type,
                  "display_name": r.display_name,
                  "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
              }
              for r in rows
          ]
  ```

- [ ] 9.2 Add `GET /api/pvi/history`

  Returns last `?days=N` (default 7) `PVIDailyScore` rows ordered by date ascending.

  ```python
  @router.get("/pvi/history")
  def get_pvi_history(days: int = 7) -> list[dict[str, Any]]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import PVIDailyScore
      from datetime import date, timedelta
      settings = get_settings()
      cutoff = date.today() - timedelta(days=days)
      with get_db() as db:
          rows = (
              db.query(PVIDailyScore)
              .filter(
                  PVIDailyScore.user_id == settings.default_user_id,
                  PVIDailyScore.date >= cutoff,
              )
              .order_by(PVIDailyScore.date)
              .all()
          )
          return [
              {"date": r.date.isoformat(), "score": r.score, "regime": r.regime}
              for r in rows
          ]
  ```

- [ ] 9.3 Add `GET /api/replies`, `POST /api/replies/{id}/send`, `POST /api/replies/{id}/dismiss`, `POST /api/replies/{id}/update`

  `GET /api/replies` joins `ReplyDraft → Message` to filter by `user_id`. Returns `sender` and `subject` (from `Message`) alongside draft fields.

  ```python
  @router.get("/replies")
  def get_replies() -> list[dict[str, Any]]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import ReplyDraft, Message
      settings = get_settings()
      with get_db() as db:
          rows = (
              db.query(ReplyDraft, Message)
              .join(Message, ReplyDraft.message_id == Message.id)
              .filter(
                  Message.user_id == settings.default_user_id,
                  ReplyDraft.status == "proposed",
              )
              .order_by(ReplyDraft.created_at.desc())
              .all()
          )
          return [
              {
                  "id": str(r.id),
                  "message_id": str(r.message_id),
                  "tone": r.tone,
                  "draft_text": r.draft_text,
                  "status": r.status,
                  "created_at": r.created_at.isoformat(),
                  "sender": m.sender,
                  "subject": m.title,
              }
              for r, m in rows
          ]


  @router.post("/replies/{reply_id}/send")
  def send_reply(reply_id: str) -> dict[str, Any]:
      from core.db.engine import get_db
      from core.db.models import ReplyDraft
      from datetime import datetime, timezone
      with get_db() as db:
          draft = db.query(ReplyDraft).filter(ReplyDraft.id == reply_id).first()
          if not draft:
              from fastapi import HTTPException
              raise HTTPException(status_code=404, detail="Reply draft not found")
          draft.status = "sent"
          # Note: actual Gmail send is handled by the reply workflow in apps/bot/
          # For web app MVP, mark as sent in DB only. Wire Gmail send in a follow-up.
          return {"id": reply_id, "status": "sent"}


  @router.post("/replies/{reply_id}/dismiss")
  def dismiss_reply(reply_id: str) -> dict[str, Any]:
      from core.db.engine import get_db
      from core.db.models import ReplyDraft
      with get_db() as db:
          draft = db.query(ReplyDraft).filter(ReplyDraft.id == reply_id).first()
          if not draft:
              from fastapi import HTTPException
              raise HTTPException(status_code=404, detail="Reply draft not found")
          draft.status = "dismissed"
          return {"id": reply_id, "status": "dismissed"}


  class UpdateReplyBody(BaseModel):
      draft_text: str


  @router.post("/replies/{reply_id}/update")
  def update_reply(reply_id: str, body: UpdateReplyBody) -> dict[str, Any]:
      from core.db.engine import get_db
      from core.db.models import ReplyDraft
      with get_db() as db:
          draft = db.query(ReplyDraft).filter(ReplyDraft.id == reply_id).first()
          if not draft:
              from fastapi import HTTPException
              raise HTTPException(status_code=404, detail="Reply draft not found")
          draft.draft_text = body.draft_text
          return {"id": reply_id, "status": "updated"}
  ```

  Add `from pydantic import BaseModel` to the top of `dashboard_api.py` (currently only `from fastapi import APIRouter, Depends`).

- [ ] 9.4 Add digest endpoints: `GET /api/digest/today`, `GET /api/digest/weekly`, `POST /api/digest/generate`

  ```python
  @router.get("/digest/today")
  def get_digest_today() -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import Digest
      from datetime import date
      settings = get_settings()
      with get_db() as db:
          row = (
              db.query(Digest)
              .filter(
                  Digest.user_id == settings.default_user_id,
                  Digest.date == date.today(),
              )
              .order_by(Digest.generated_at.desc())
              .first()
          )
          if not row:
              # On-demand generation: call generate_digest() if no row exists
              try:
                  from core.digest import generate_digest  # adjust import to actual module path
                  generate_digest(user_id=str(settings.default_user_id))
                  row = (
                      db.query(Digest)
                      .filter(
                          Digest.user_id == settings.default_user_id,
                          Digest.date == date.today(),
                      )
                      .order_by(Digest.generated_at.desc())
                      .first()
                  )
              except Exception:
                  pass  # fail-soft: return null if generation fails
          if not row:
              return {"date": date.today().isoformat(), "content_md": "", "regime": "normal", "generated_at": None}
          return {
              "date": row.date.isoformat(),
              "content_md": row.content_md,
              "regime": row.regime,
              "generated_at": row.generated_at.isoformat(),
          }


  @router.get("/digest/weekly")
  def get_digest_weekly() -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import Digest
      settings = get_settings()
      with get_db() as db:
          row = (
              db.query(Digest)
              .filter(
                  Digest.user_id == settings.default_user_id,
                  Digest.regime == "weekly",
              )
              .order_by(Digest.generated_at.desc())
              .first()
          )
          if not row:
              return {"date": None, "content_md": "", "regime": "weekly", "generated_at": None}
          return {
              "date": row.date.isoformat(),
              "content_md": row.content_md,
              "regime": row.regime,
              "generated_at": row.generated_at.isoformat(),
          }


  @router.post("/digest/generate")
  def generate_digest_endpoint() -> dict[str, Any]:
      from core.config import get_settings
      settings = get_settings()
      try:
          from core.digest import generate_digest  # adjust import to actual module path
          generate_digest(user_id=str(settings.default_user_id))
          return {"status": "ok"}
      except Exception as e:
          from fastapi import HTTPException
          raise HTTPException(status_code=500, detail=str(e))
  ```

  Important: The `generate_digest` import path must match the actual module in `packages/core/src/core/`. Check with:

  ```bash
  PYTHONPATH=packages/core/src python3 -c "from core.digest import generate_digest; print('ok')"
  ```

  Adjust the import path if the function lives elsewhere (e.g., `core.digest_generator`).

- [ ] 9.5 Add focus endpoints: `GET /api/focus/status`, `POST /api/focus/start`, `POST /api/focus/end`

  ```python
  @router.get("/focus/status")
  def get_focus_status() -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import FocusSession
      settings = get_settings()
      with get_db() as db:
          session = (
              db.query(FocusSession)
              .filter(
                  FocusSession.user_id == settings.default_user_id,
                  FocusSession.is_active == True,
              )
              .order_by(FocusSession.started_at.desc())
              .first()
          )
          if not session:
              return {"is_active": False, "started_at": None, "ends_at": None, "session_id": None}
          return {
              "is_active": True,
              "started_at": session.started_at.isoformat(),
              "ends_at": session.ends_at.isoformat(),
              "session_id": str(session.id),
          }


  class StartFocusBody(BaseModel):
      duration_minutes: int


  @router.post("/focus/start")
  def start_focus(body: StartFocusBody) -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import FocusSession
      from datetime import datetime, timezone, timedelta
      settings = get_settings()
      with get_db() as db:
          # End any existing active session first
          db.query(FocusSession).filter(
              FocusSession.user_id == settings.default_user_id,
              FocusSession.is_active == True,
          ).update({"is_active": False, "ended_early_at": datetime.now(timezone.utc)})
          now = datetime.now(timezone.utc)
          session = FocusSession(
              user_id=str(settings.default_user_id),
              started_at=now,
              ends_at=now + timedelta(minutes=body.duration_minutes),
              is_active=True,
          )
          db.add(session)
          db.flush()
          session_id = str(session.id)
      return {"session_id": session_id, "status": "started"}


  @router.post("/focus/end")
  def end_focus() -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import FocusSession
      from datetime import datetime, timezone
      settings = get_settings()
      with get_db() as db:
          updated = db.query(FocusSession).filter(
              FocusSession.user_id == settings.default_user_id,
              FocusSession.is_active == True,
          ).update({
              "is_active": False,
              "ended_early_at": datetime.now(timezone.utc),
          })
          return {"status": "ended", "sessions_closed": updated}
  ```

- [ ] 9.6 Add `GET /api/search`

  ILIKE on `ActionItem.title`, `Message.title`, `Message.sender`.

  ```python
  @router.get("/search")
  def search(q: str = "") -> dict[str, Any]:
      from core.config import get_settings
      from core.db.engine import get_db
      from core.db.models import ActionItem, Message
      settings = get_settings()
      if not q.strip():
          return {"tasks": [], "messages": []}
      pattern = f"%{q}%"
      with get_db() as db:
          tasks = (
              db.query(ActionItem)
              .filter(
                  ActionItem.user_id == settings.default_user_id,
                  ActionItem.title.ilike(pattern),
              )
              .limit(20)
              .all()
          )
          messages = (
              db.query(Message)
              .filter(
                  Message.user_id == settings.default_user_id,
                  (Message.title.ilike(pattern) | Message.sender.ilike(pattern)),
              )
              .order_by(Message.message_ts.desc())
              .limit(20)
              .all()
          )
          return {
              "tasks": [
                  {
                      "id": str(t.id),
                      "title": t.title,
                      "details": t.details,
                      "due_at": t.due_at.isoformat() if t.due_at else None,
                      "priority": t.priority,
                      "status": t.status,
                  }
                  for t in tasks
              ],
              "messages": [
                  {
                      "id": str(m.id),
                      "sender": m.sender,
                      "title": m.title,
                      "body_preview": m.body_preview,
                      "message_ts": m.message_ts.isoformat(),
                      "summary_short": None,
                  }
                  for m in messages
              ],
          }
  ```

- [ ] 9.7 Run the API and verify all new endpoints

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/api/src \
    uvicorn api.main:app --reload --port 8000
  ```

  Test each endpoint:

  ```bash
  # Sources
  curl -s http://localhost:8000/api/sources | python3 -m json.tool

  # PVI history
  curl -s "http://localhost:8000/api/pvi/history?days=7" | python3 -m json.tool

  # Replies
  curl -s http://localhost:8000/api/replies | python3 -m json.tool

  # Digest today
  curl -s http://localhost:8000/api/digest/today | python3 -m json.tool

  # Focus status
  curl -s http://localhost:8000/api/focus/status | python3 -m json.tool

  # Search
  curl -s "http://localhost:8000/api/search?q=test" | python3 -m json.tool
  ```

  All endpoints must return 200 (empty arrays/objects are fine; 500s are not).

- [ ] 9.8 Run existing tests to confirm no regressions

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/api/src \
    python3 -m pytest tests/unit/ -v --tb=short
  ```

  All 135 tests must still pass.

- [ ] 9.9 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/api/src/api/routes/dashboard_api.py
  git commit -m "feat(api): add replies, digest, focus, search, sources, pvi/history endpoints"
  ```

---

## Task 10: Mobile polish + deployment config

**Scope:** Verify mobile layout, Next.js Docker config, Docker Compose update, README additions.

**Files created/modified:**
- `apps/web/next.config.ts` (modify)
- `apps/web/Dockerfile` (create)
- `infra/docker-compose.yml` (modify)
- `README.md` (modify)

### Steps

- [ ] 10.1 Mobile layout verification

  Open Chrome DevTools → toggle device emulation to iPhone 14 Pro (390px wide). Navigate to each page and verify:
  - `/tasks`: bottom nav visible, task rows not clipped, filter tabs scroll horizontally
  - `/inbox`: source filter tabs scroll horizontally, message rows readable
  - `/digest`: PVI card fills width, sparkline scales correctly
  - `/replies`: reply cards full-width, action buttons not cramped
  - `/search`: input full-width, auto-focus fires on iOS (may be blocked by browser — acceptable)
  - `/focus`: countdown centred, duration buttons wrap gracefully

  Fix any layout issues found before continuing.

- [ ] 10.2 Update `apps/web/next.config.ts`

  ```ts
  // apps/web/next.config.ts
  import type { NextConfig } from "next";

  const nextConfig: NextConfig = {
    output: "standalone",
    // API requests proxied to FastAPI in development
    // In production, set NEXT_PUBLIC_API_BASE_URL to the API service URL
  };

  export default nextConfig;
  ```

- [ ] 10.3 Create `apps/web/Dockerfile`

  Multi-stage build using `output: standalone`. The final image is ~150MB.

  ```dockerfile
  # apps/web/Dockerfile
  FROM node:20-alpine AS base

  # Install pnpm
  RUN corepack enable && corepack prepare pnpm@latest --activate

  # ---- deps ----
  FROM base AS deps
  WORKDIR /app
  COPY package.json pnpm-lock.yaml* ./
  RUN pnpm install --frozen-lockfile

  # ---- builder ----
  FROM base AS builder
  WORKDIR /app
  COPY --from=deps /app/node_modules ./node_modules
  COPY . .
  ENV NEXT_TELEMETRY_DISABLED=1
  RUN pnpm build

  # ---- runner ----
  FROM base AS runner
  WORKDIR /app
  ENV NODE_ENV=production
  ENV NEXT_TELEMETRY_DISABLED=1

  RUN addgroup --system --gid 1001 nodejs && \
      adduser --system --uid 1001 nextjs

  COPY --from=builder /app/public ./public
  COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
  COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

  USER nextjs
  EXPOSE 3000
  ENV PORT=3000
  ENV HOSTNAME="0.0.0.0"

  CMD ["node", "server.js"]
  ```

- [ ] 10.4 Update `infra/docker-compose.yml` — add `web` service

  Add to the existing `services` block (before `volumes:`):

  ```yaml
    web:
      build:
        context: ../apps/web
        dockerfile: Dockerfile
      environment:
        NEXT_PUBLIC_API_BASE_URL: http://api:8000
        NEXT_PUBLIC_API_KEY: ${DASHBOARD_API_KEY:-}
      ports:
        - "127.0.0.1:3000:3000"
      depends_on:
        - api
      restart: unless-stopped
  ```

  The `api` service remains on `127.0.0.1:8000:8000` (no changes needed). The `web` service accesses `api` via Docker internal DNS (`http://api:8000`).

- [ ] 10.5 Add web app section to `README.md`

  Find the existing "Getting Started" or "Usage" section and add after it:

  ```markdown
  ## Web App

  The Next.js web app runs at `http://localhost:3000` and provides a full browser-based UI.

  ### Local development

  ```bash
  cd apps/web
  pnpm install
  pnpm dev
  ```

  The app proxies API calls to `http://localhost:8000` by default. Ensure the FastAPI server is running:

  ```bash
  PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/api/src \
    uvicorn api.main:app --reload --port 8000
  ```

  ### Docker (all services)

  ```bash
  docker compose -f infra/docker-compose.yml up --build
  ```

  Access:
  - Web app: http://localhost:3000
  - API (direct): http://localhost:8000

  ### Environment variables

  | Variable | Default | Purpose |
  |----------|---------|---------|
  | `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | FastAPI base URL |
  | `NEXT_PUBLIC_API_KEY` | `` (empty) | API key if `DASHBOARD_API_KEY` is set |
  ```

- [ ] 10.6 Build Docker image to verify

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps/apps/web
  docker build -t clawdbot-web .
  ```

  Expected: build completes, final image present in `docker images`.

- [ ] 10.7 Commit

  ```bash
  cd /Users/aryanganju/Desktop/Code/LifeOps
  git add apps/web/next.config.ts apps/web/Dockerfile infra/docker-compose.yml README.md
  git commit -m "feat(web): add Docker config, docker-compose web service, README web section"
  ```

---

## Dependency order

Tasks can be executed in this order (each unblocked once prior task is done):

```
Task 1 (Scaffold)
  └── Task 2 (Layout)
        ├── Task 3 (/tasks)
        ├── Task 4 (/inbox)
        ├── Task 5 (/digest)  — also uses PVICard, recharts
        ├── Task 6 (/replies)
        ├── Task 7 (/search)  — uses TaskRow from Task 3
        └── Task 8 (/focus)   — uses PVICard from Task 5
Task 9 (FastAPI endpoints) — independent, can run in parallel with Tasks 2-8
Task 10 (Docker + polish) — depends on Tasks 1-9 all complete
```

Tasks 3-8 can run in parallel after Task 2 completes. Task 9 can start immediately after Task 1.

## CORS note

If the Next.js dev server (`localhost:3000`) calls FastAPI (`localhost:8000`) and gets CORS errors, add to `apps/api/src/api/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Do not add wildcard CORS in production — scope to the actual deployed domain.

## Success criteria

- [ ] `http://localhost:3000` redirects to `/tasks` and renders the full layout
- [ ] All 6 pages render without console errors
- [ ] `/tasks` accept/dismiss calls update the database (verify via `claw today`)
- [ ] `/inbox` source tabs filter correctly
- [ ] `/digest` Regenerate button produces a new digest row
- [ ] `/replies` Send marks `status="sent"` in `reply_drafts` table
- [ ] `/search` returns matching tasks and messages within 300ms debounce
- [ ] `/focus` countdown ticks in real-time and End Focus clears `is_active`
- [ ] Mobile layout verified at 390px: all pages usable, no overflow
- [ ] `pnpm build` exits 0 with 0 TypeScript errors
- [ ] `docker build -t clawdbot-web apps/web/` succeeds
- [ ] 135 existing Python unit tests still pass
