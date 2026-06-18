# GTM OS — Running & Usage Guide

A local-first operating system for running a portfolio of projects, products,
profiles, and content from your machine. Files are the source of truth; everything
else is derived from them.

---

## Prerequisites

- **Python 3** (preinstalled on macOS) — `python3 --version`
- **`claude` CLI**, logged in — `claude --version` (used for content + guideline AI jobs)

No other install. No server, no database to run, no `npm`.

---

## Quick start — the dashboard

```bash
cd /path/to/my-os
python3 dashboard/server.py
```

It re-indexes from your files, then prints:

```
GTM OS dashboard → http://127.0.0.1:8765
```

Open that URL. Stop the server with `Ctrl-C`. Pass `--port 9000` to change the
port, or `--no-reindex` to skip the startup rebuild.

### The layout

Three panels, left to right:

| Panel | What it's for |
|---|---|
| **Projects** (left rail) | Navigation tree. *Across everything* group at top; each project below it. Click a project to expand its sections; click a section or profile to load it in the Workspace. |
| **Workspace** (center) | The selected view — changes based on what you click in the rail. |
| **Consultant** (right) | The always-present AI advisor — arriving in a later build; a static placeholder for now. |

**Projects rail detail**

The *Across everything* group contains:

- **Needs you** — items waiting on your input or decision.
- **Operations** — cross-project to-dos and operational tasks.
- **Calendar** — month grid of all dated items across every project, today highlighted, ‹ Today › month navigation.

Each project expands into six sections:

> **Overview / Problem & validation / Experiments / Positioning & pricing / Product / Operations**

**Profiles** (your content presences) are nested inside each project. Click a profile to open its content board. Each profile has one or more **channels** (per-platform accounts).

**Workspace views**

- **Project section** — shows that section's data.
- **Profile content board** — plain stages **Idea → Draft → Scheduled → Published**, with row actions **＋ Add idea / ✦ Generate ideas / Edit / Delete**.
- **Calendar** — same month grid described above.

---

## The content pipeline (two stages)

The system splits **cheap idea → expensive content** so you never generate posts
you'll throw away.

1. **Plan** = a calendar of lightweight idea-slots (date, channel targets, pillar, concept).
2. **Expand to full content** = turn one *approved* idea into the finished post
   (hook, caption, structure, hashtags, CTA, visual brief + AI-image prompt).

Status flow (each step is a button on the board):

```
planned → approved_slot → briefed → approved → scheduled → published
                                  (rejected at any point)
```

Content generation uses the **VOICE CASCADE**: project voice (`project.md` body)
→ profile voice (`profile.md` body) → channel guidelines (`channels/<slug>/guidelines.md`).
All three layers are injected automatically.

Generating a new plan (more ideas on the board):

```bash
python3 generate.py plan <profile-slug> \
  --period "2026-06-30 to 2026-07-13" \
  --platforms tiktok,instagram --cadence 3 \
  --focus "optional steer, e.g. push the launch"
# then refresh the dashboard
```

`<profile-slug>` is looked up under `projects/*/profiles/<profile-slug>/` automatically.

Expanding one slot from the terminal (same as the board button):

```bash
python3 generate.py brief <profile-slug> <post-id>
```

---

## Channel guidelines

Each channel has `projects/<project-slug>/profiles/<profile-slug>/channels/<channel-slug>/guidelines.md`
with a `## General` section plus per-platform sections (`## Instagram`, `## TikTok`, …).
These are **injected into every generation** for that channel via the voice cascade,
so your rules ("on IG always Reels", "end with a question") are actually followed.

Edit them in the **Channels** tab on the profile board. **Refine with AI** sends
rough notes through `claude -p` and returns clean structured guidelines into the
editor — review, then **Save** (it doesn't save until you do).

The refine command:
```bash
echo "rough notes..." | python3 generate.py refine-guidelines <channel-slug>
```

`<channel-slug>` is looked up under `projects/*/profiles/*/channels/<channel-slug>/` automatically.

---

## How it works (the one invariant)

```
authored files ──index──▶ database/data/os.db (read-only) ──▶ dashboard views
      ▲                                                          │
      └──────── mutate FILE ◀── dashboard action ──▶ re-index ───┘
```

- **Authored files = source of truth** (markdown + JSON you write/edit).
- **`os.db` = a derived, disposable index** — fully rebuilt from the files by
  `index.py`. Never hand-edit it; deleting it is safe.
- The **dashboard mutates files, then re-indexes** — it never writes `os.db`
  directly (its DB connection is read-only, so it physically can't).
- A **PostToolUse hook** re-indexes automatically when a source file changes.

Rebuild the index manually anytime (rarely needed):

```bash
python3 index.py
```

---

## Where things live

```
my-os/
├── docs/                    ← this guide
├── database/                ← all DB stuff (the only db-related folder)
│   ├── migrations/          ← schema (0001_init.sql); index.py applies *.sql in order
│   └── data/os.db           ← derived index, regenerated (gitignored)
├── index.py                 ← builds os.db from the files
├── generate.py              ← claude -p jobs: plan, brief, refine-guidelines
├── prompts/                 ← prompt templates + platform constraints
├── hooks/reindex.py         ← auto re-index on source edits (PostToolUse)
├── dashboard/               ← db.py (read), fileops.py (write), server.py, app.html
├── portfolio/               ← activities.md, milestones.json
└── projects/                ← all projects (nested: strategy/, products/, profiles/, channels/)
    └── <project-slug>/
        ├── project.md       ← project voice + metadata
        ├── strategy/        ← intake.md, memos/, experiments/
        ├── products/<slug>/ ← roadmap.md
        └── profiles/<slug>/ ← profile.md, content/, channels/<slug>/
```

---

## Typical session

1. `python3 dashboard/server.py` → open the URL
2. Review the **Content board**; reject weak ideas, approve good ones
3. **Expand to full content** on the approved ones; read them in the drawer
4. Spot a recurring rule? Add it in **Channels** → Refine → Save
5. Need more ideas? `python3 generate.py plan <profile-slug> …`, then refresh
6. Strategy work (intake, memos, experiments) is edited as files under
   `projects/<slug>/strategy/`; the dashboard reflects them after a re-index.
