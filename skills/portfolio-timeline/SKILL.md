---
name: portfolio-timeline
description: Build or rebuild the unified timeline across all projects, profiles, products, content, experiments, and launches. Use for "show me everything", "what's on the calendar", "unified view", or after any significant planning update.
---

# Portfolio Timeline

Reads everything. Synthesizes one chronological view.

## Data source: query `os.db` first, files as fallback
The fast path is the SQLite index — build the timeline from one query, not by
re-reading every file:
```sql
SELECT * FROM timeline ORDER BY date;   -- VIEW unioning the rows below
```
`timeline` unions: experiments (status + duration), content posts (slot status),
product features/releases, manual activities, and milestones — each joined to
`entities` for priority and `hours_per_week`.

**If `os.db` is missing or stale** (older than the newest source file), fall back
to reading the source files in this order, then recommend rebuilding the index:
1. `projects/*/project.md` — entity map, priorities, hours_per_week
2. `portfolio/milestones.json` — manual deadlines, releases, external events
3. `portfolio/activities.md` — manual tasks / micro-items
4. Per project: `strategy/intake.md` (goals, hours), `strategy/memos/` (latest pace/channel/launch),
   `strategy/experiments/` (status + duration)
5. Per profile: `profiles/<slug>/content/` (plans + slot statuses)
6. Per product: `products/<slug>/roadmap.md` (features + releases)

Cross-reference: profiles/products linked to a project inherit links to that project's
launch/experiment dates automatically.

## Output: `portfolio/timeline-<date>.json` + readable display

### JSON schema
```json
{
  "generated": "<date>",
  "period": "<start> to <end>",
  "entries": [
    {
      "id": "entry-001",
      "date": "YYYY-MM-DD",
      "date_end": "YYYY-MM-DD or null",
      "entity": "project-slug | profile-slug | product-slug | channel-slug",
      "entity_type": "project | profile | product | channel | external",
      "type": "experiment | content | launch | milestone | release | review | deadline | external",
      "title": "short label",
      "status": "planned | running | approved | done | blocked",
      "priority": "critical | high | normal | low",
      "linked_to": ["other entry ids this depends on or aligns with"],
      "notes": ""
    }
  ],
  "resource_note": "plain-language summary of weekly load across all entities"
}
```

### Readable display
Present as a calendar table grouped by week, then day.
Columns: Date | Entity | Type | Title | Status | Linked to.
Entries for multiple entities on the same date are shown on separate rows.

## Auto-detect and surface (run after building the table)

Flag these — do not silently ignore them:

- **[CONFLICT]** weeks where planned work exceeds intake hours across projects
- **[OPPORTUNITY]** a project launch within 3 weeks with no profile content ramp planned
- **[ORPHAN]** profile content referencing a product feature not yet shipped or approved
- **[STALE]** experiments marked "running" past their stated duration with no result logged,
  or product features stuck in "building" with no shipped date and no recent update
- **[RELEASE]** a product release within 3 weeks (or just shipped) on a product linked to a
  profile, with no content ramp planned — route to product-build / content-plan
- **[GAP]** periods with no activity on a primary project
- **[MISALIGNED]** profile tone in content plan doesn't match the project's current phase
  (e.g., launch-tone content while the project is still in quiet validation)

For each flag: state the issue, the entities involved, and which skill fixes it.

## Rules
- A content post for Profile X linked to Project A's launch appears once but with
  both entity labels in the "entity" field.
- If a source file is missing, note the gap explicitly — never silently skip it.
- This is a DERIVED view. Rebuild it (rerun this skill) any time a launch plan,
  content plan, or experiment timeline changes.
- Never use this file as the source of truth for editing — always edit the source
  files (project strategy, profile content plans) and rebuild.
