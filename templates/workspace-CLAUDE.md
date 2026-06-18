# Copy this file to your workspace root as `CLAUDE.md`.
# It is auto-loaded every session, so keep it short — every line costs context.

# Portfolio OS — operating context

This workspace runs a GTM operating system. Scope: **one deep vertical (GTM)**,
a **product-building layer** (product roadmaps — app, physical, or service), and
a **thin activities/micro-feature layer** for manual items that just need
organizing and checking off. Across all of it, the front of the loop is
**problem validation** — validate the problem is real before any build or GTM work.

## Storage model (hybrid — do not violate)
- **Files are the source of truth** for authored prose: `strategy/intake.md`,
  `profile.md`, `project.md`, and the memo/brief JSON.
- **`os.db` (local SQLite) is a DERIVED index** — entities, links, statuses,
  dates, experiment outcomes, content slots. It is disposable: rebuildable from
  files. Never hand-edit it.
- Coordination skills (timeline, sync, weekly-review) **query `os.db`**.
  Authoring skills open files. Don't re-read every file to coordinate.
- No DB server (no Postgres/MySQL/Supabase) until a UI or multi-user need exists.

## File conventions
Everything lives under `projects/<project-slug>/`:
- `projects/<slug>/project.md` — project identity + overall voice (kind: venture|brand; priority; hours_per_week; status)
- `projects/<slug>/strategy/intake.md` — venture facts + `## Evidence log`
- `projects/<slug>/strategy/memos/<type>-vN.json` — decision memos, versioned, never overwritten
- `projects/<slug>/strategy/experiments/` — experiment designs + logged results
- `projects/<slug>/products/<product-slug>/roadmap.md` — product features + micro-features (markdown checklist, hand-edited)
- `projects/<slug>/profiles/<profile-slug>/profile.md` — profile voice (topic + voice for a content presence)
- `projects/<slug>/profiles/<profile-slug>/content/` — content plans + briefs (JSON)
- `projects/<slug>/profiles/<profile-slug>/channels/<channel-slug>/channel.md` — per-channel account (frontmatter: platform)
- `projects/<slug>/profiles/<profile-slug>/channels/<channel-slug>/guidelines.md` — per-channel posting guidelines
- `portfolio/activities.md` — manual non-GTM tasks/micro-items (markdown checklist, hand-edited)
- `portfolio/milestones.json`, `portfolio/timeline-<date>.json`

## Voice cascade (content generation)
`project.md` body → `profile.md` body → `channels/<channel-slug>/guidelines.md`
All three layers are injected into every content generation job.

## The loop
problem-validation → venture-intake → gtm-assessment → channel-strategy →
experiment-design → (run it) → experiment-review → evidence logged → rerun assessment.
Profiles/content hang off an approved channel mandate. Product work lives in
`products/<slug>/roadmap.md` (releases trigger a content ramp). Add manual micro-
features/tasks straight into the roadmap or `activities.md` and tick them off.
Coordination = timeline + sync + weekly-review (all query `os.db`).

## Hard rules
1. Read `strategy/intake.md` + the evidence log + recent memos before any strategy skill.
2. Every strategic output is a DECISION MEMO: 2–4 options, pros/cons, one
   recommendation, and what evidence would change it. Never a single take-it-or-leave-it plan.
3. Cite which intake facts drove each recommendation.
4. Missing evidence = say "unvalidated assumption". Never fake confidence.
5. `accelerate` pace calls are forbidden while problem validation is weak/unvalidated.
6. New memo = new version; old memos marked superseded, not deleted.
7. Slugs are immutable lowercase-kebab identifiers; never reuse after archiving.

When in doubt about routing, invoke the `gtm-os` skill.
