# BUILD.md — build sequence for the OS backend

The 21 skills already run **file-based** today. This document is the order to
build the automation around them: the `claude -p` generation pipeline, the
SQLite index, the rebuild hook, and the dashboard. Build against **real files**,
never ahead of them.

Schemas live in `templates/gtm-layer-spec.md` (entities, relationships, memos,
experiments, activities, features, milestones) and `templates/generation-spec.md`
(posts, jobs). Collapse them into one `schema.sql` as step one of the indexer.

---

## Three data categories (the one invariant)

1. **Authored content → files, source of truth.** `intake.md`, `identity.md`,
   relationship/roadmap/activity markdown, and the memo/brief/plan JSON.
2. **Derived index → `os.db`, disposable.** Rebuilt from the files above. Never
   hand-edited; safe to `rm` and regenerate.
3. **Ephemeral runtime → DB-only, fine to lose.** A `jobs` queue, *if* you add
   one. Not source of truth.

If a write doesn't fit (1), it must be reducible to (2) by re-running the
indexer. The dashboard mutates **files**, then re-indexes — see Phase 3.

---

## Critical path

```
Phase 0 (seed data) → [ Track A: claude -p pipeline  ∥  Track B: indexer ] → rebuild hook → dashboard
```
A and B are independent (A writes files, B reads files). Build in parallel.
The dashboard is gated by both.

---

## Phase 0 — Seed real data (no code)

Use the OS file-based to create real inputs to build against:
`problem-validation → venture-intake → gtm-assessment` for one venture, one
`apps/<slug>/roadmap.md`, one brand `identity.md`, a few `activities.md` lines,
and `portfolio/relationships.md` via `portfolio-map`. Purpose: catch schema and
file-convention bugs in cheap markdown, not in code.

---

## Phase 1, Track A — `claude -p` generation pipeline

Wire the plan + brief jobs (optionally the strategy-memo jobs) from
`generation-spec.md`. Self-contained: needs only file conventions + schemas.

- Invocation (verified, CC 2.1+): `identity.md` is content — pipe it, don't use
  `--append` (no such flag):
  ```bash
  cat brands/<slug>/identity.md | claude -p "$(cat prompts/plan.txt)" --output-format json
  ```
- Validate JSON before writing; on parse failure retry once with the error
  appended, then mark failed.
- Write outputs to the file locations the skills already use (e.g.
  `brands/<slug>/content/plan-<period>.json`, `.../briefs/<id>.json`).
- **Skip the `jobs` queue table for now** — run jobs synchronously. A queue only
  earns its place once you batch many or go async.

---

## Phase 1, Track B — indexer + `timeline` VIEW

A single `index` script that **wipes and fully repopulates** `os.db` from files
(idempotent). `PRAGMA foreign_keys = ON;` insert `entities` first (FKs).

### Source file → table map
| Source file | Table(s) | Notes |
|---|---|---|
| `portfolio/relationships.md` | `entities`, `relationships` | primary structured source for entity rows + edges |
| `ventures/<slug>/intake.md` | `entities.hours_per_week`, `file_path` | parse hours; evidence-log prose is NOT indexed |
| `ventures/<slug>/memos/<type>-vN.json` | `memos` | `type` = filename stem; `version` from `vN` |
| `ventures/<slug>/experiments/*.json` | `experiments` | status, duration, decision, result |
| `brands/<slug>/content/plan-*.json` + `briefs/` | `posts` | one row per slot; status from the file |
| `apps/<slug>/roadmap.md` | `features` | parse the `- [ ] / - [x]` checklist |
| `portfolio/activities.md` | `activities` | parse the checklist |
| `portfolio/milestones.json` | `milestones` | direct JSON load |

### `timeline` VIEW
`CREATE VIEW timeline AS` a `UNION ALL` over `experiments`, `posts`, `features`,
`activities`, `milestones`, normalized to a common shape
(`date, date_end, entity_slug, kind, title, status, priority`) and joinable to
`entities` for priority + `hours_per_week`. This single VIEW is what
`portfolio-timeline` / `portfolio-sync` / `weekly-review` query.

---

## Phase 2 — rebuild hook

Once the `index` script is verified by hand, add a `PostToolUse` hook (or a
file-watcher) that reruns it when a source file changes. Automate only after the
script is proven — automating an unverified script hides bugs.

---

## Phase 3 — dashboard (last; consumes A + B)

Reads `os.db` for views (timeline, content pipeline board, roadmaps) and
enqueues `claude -p` jobs (approve-slot → brief-job loop).

**Write model — dashboard mutates FILES, not the DB.** A status change or edit
writes back to the source file (a field/frontmatter), then triggers a re-index.
This keeps the invariant intact and gives you git history for free. Do **not**
let the dashboard write straight into `os.db` — that splits the source of truth.

Pipeline status state machine (lives in the file, mirrored to `posts.status`):
`planned → approved_slot → briefed → approved → scheduled → published`
(`rejected` at any review point). Edits create a new version, never overwrite.

---

## Gotchas / best practices

- **Entity facts come from `relationships.md`, not by parsing each `intake.md`.**
  `intake.md` is freeform prose — only pull `hours_per_week` from it (or, cleaner,
  have `portfolio-map` capture hours into `relationships.md` so the indexer never
  parses prose). Decide this before writing the parser.
- **Keep checklist lines parseable.** Fix one format, e.g.
  `- [ ] title — why — priority: high — target: 2026-07-01`, split on ` — `.
- **`memos.status`** (proposed/approved/superseded): default `proposed` on index
  unless the memo file or dashboard says otherwise.
- **Slug integrity** is assumed by every FK — run `portfolio-map`'s slug check
  (or replicate it in the indexer) and fail loudly on an unresolved slug rather
  than inserting orphans.
- **Stack:** stdlib is enough — Python `sqlite3` (or Node `better-sqlite3`) for
  the indexer; a thin local app for the dashboard. No ORM, no server DB, no
  framework you'd maintain. Lean and local, per the project's storage rule.
