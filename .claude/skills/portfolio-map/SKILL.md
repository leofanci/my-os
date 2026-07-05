---
name: portfolio-map
description: Scaffold the folder structure for a new project, profile, product, or channel. Use when setting up the OS for the first time, adding a new entity, or when "my profile X is connected to project Y".
---

# Portfolio Map

Goal: scaffold and maintain the `projects/<slug>/` folder structure — the file
hierarchy that is the source of truth for every entity in the portfolio.

No `relationships.md` — structure comes from filesystem nesting.

## Interview approach
Max 3 questions at a time. Cover:
- What projects exist (slug, name, kind: venture|brand, priority, status, hours/week)
- What profiles exist under each project (slug, name, topic/niche)
- What products exist under each project (slug, name, type: app|physical|service)
- What channels exist under each profile (slug, platform)
- Shared dependencies ("Profile X and Profile Y both link to the same product")
- External events that should appear on the timeline (investors, partners, hard deadlines)

## Scaffold action (what this skill creates/updates)

For each new project:
```
projects/<project-slug>/
    project.md          ← frontmatter: name, kind, priority, hours_per_week, status; body = overall voice
    strategy/           ← (venture projects) intake.md, memos/, experiments/
    products/           ← (optional) product sub-folders
    profiles/           ← profile sub-folders
```

For each new profile under a project:
```
projects/<project-slug>/profiles/<profile-slug>/
    profile.md          ← frontmatter: name, topic; body = profile voice
    content/            ← plan-<period>.json, briefs/
    channels/           ← channel sub-folders
```

For each new channel under a profile:
```
projects/<project-slug>/profiles/<profile-slug>/channels/<channel-slug>/
    channel.md          ← frontmatter: platform; body = per-platform notes
    guidelines.md       ← per-channel posting guidelines (edited in dashboard)
```

For each new product under a project:
```
projects/<project-slug>/products/<product-slug>/
    product.md          ← frontmatter: name, type, status
    roadmap.md          ← product features + micro-features (markdown checklist)
```

## Frontmatter starters

`project.md`:
```yaml
---
name: <Project Name>
kind: venture | brand
priority: primary | secondary | experiment
hours_per_week: <int>
status: idea | prototype | live | revenue
---
<overall project voice — injected as first layer of VOICE CASCADE>
```

`profile.md`:
```yaml
---
name: <Profile Name>
topic: <one-line topic/niche>
project: <project-slug>
---
<profile voice — pillars, tone, audience, platform goals, CTAs, hard rules>
```

`channel.md`:
```yaml
---
platform: instagram | tiktok | x | linkedin | youtube | facebook
handle: <@handle or url>
---
<per-platform notes>
```

`product.md`:
```yaml
---
name: <Product Name>
type: app | physical | service
status: idea | building | live | paused | archived
---
```

## Slug-consistency check (run after every scaffold)
After creating or updating folders, validate:
- Every `project:` reference in a profile.md matches an existing `projects/<slug>/` folder.
- Every `entity` slug in `portfolio/milestones.json` matches an existing project, profile, channel, or product folder.
- Report a `[SLUG MISMATCH]` block for each unresolved reference. Never auto-rename — surface and let the user confirm.

## Rules
- Every new project/profile/product/channel triggers a portfolio-map scaffold run.
- Never delete folders — add `status: archived` to the entity's frontmatter.
- Slugs are immutable identifiers: lowercase-kebab, never reused after archiving.
- After scaffolding, recommend running portfolio-timeline to rebuild the unified view.
