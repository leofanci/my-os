---
name: product-build
description: Manage a product roadmap - plan features, track build status, organize manually-added micro-features, and link releases to projects and profile content. Use for "what should I build next", "add a feature", "roadmap", "what's shipped", or when a release needs a content ramp.
---

# Product Build (per product)

Makes a product a first-class, active entity — not just a label on the timeline.
Source of truth is a human-editable markdown checklist you can add to and tick
off by hand: `projects/<project-slug>/products/<product-slug>/roadmap.md`.
SQLite (`features` table) just indexes it.

Products are generic: app, physical product, or service — not just web apps.

## Source of truth: `projects/<project-slug>/products/<product-slug>/roadmap.md`
```markdown
# <Product name> — Roadmap
last_updated: <date>
project: <project-slug>

## Now (building)
- [ ] feature title — one-line why — priority: high — target: 2026-07-01

## Next (planned)
- [ ] feature title — why

## Later / Ideas
- [ ] micro-feature — (add these yourself, one line is fine)

## Shipped
- [x] feature title — shipped: 2026-06-10 — release: v1.2
```

**Micro-features = one `- [ ]` line** under any section, added by hand. No
ceremony. Move it to `## Shipped` and flip to `- [x]` with a `shipped:` date
when done. That's the whole manual loop.

## What the skill does
1. **Plan a non-trivial feature**: scope (what's in/out), why now (tie to a
   project goal or user signal), dependencies, rough size. One short paragraph —
   not a decision memo. Add it under Now/Next.
2. **Organize**: read roadmap.md, group by status, flag stale `building` items
   and priority pile-ups. Keep it honest — a 12-item "Now" is a planning failure.
3. **Releases → content ramp**: when features ship as a release, if the product
   is linked to a profile, recommend running content-plan/content-brief so the
   launch isn't silent. Mirrors portfolio-sync's launch logic for releases.

## Rules
- Source of truth is the markdown file; `features` table is derived/disposable.
- A feature must say *why now* tied to evidence or a goal — not "would be cool".
- Don't let product work hide GTM reality: building features while the problem
  is unvalidated is a flag, not progress — say so (see problem-validation).
- After editing roadmap.md, recommend rebuilding the timeline.
- Micro-features stay one line; only promote to a planned feature when they grow.
