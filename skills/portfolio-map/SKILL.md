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

## Scaffold action — always via osctl, never hand-written files
Never write `project.md`/`profile.md`/`channel.md`/`product.md` by hand. Each
`create-*` command makes the subdirectories AND the frontmatter file in one
call, then reindexes. All `create-*` commands error rather than overwrite if
the slug exists, and only ever touch the one entity being created.

- **Project**: `create-project --slug <slug> --name "<Name>" --kind venture|brand --priority primary|secondary|experiment --hours-per-week <int> --status idea|prototype|live|revenue [--voice "<voice>"]`. Creates `project.md` (name/kind/priority/hours_per_week/status; body=voice) + `strategy/` (venture: intake.md via create-intake, memos/, experiments/) + `products/` + `profiles/`. Edit (slug fixed): `update-project --slug <slug> [--name] [--kind] [--priority] [--status] [--hours-per-week]`.
- **Profile**: `create-profile --project <project-slug> --slug <slug> --name "<Name>" --topic "<niche>"`. Creates `profile.md` (name/topic/project, no body) + `voices/` (vc1.md... via brand-identity skill) + `brief-specs/` (br1.md... via content-brief skill) + `content/briefs/` + `channels/`. Edit: `update-profile --slug <slug> [--name] [--topic]`.
- **Channel**: `create-channel --profile <profile-slug> --slug <slug> --platform instagram|tiktok|x|linkedin|youtube|facebook [--handle <@handle>]`. Creates `channel.md` (platform/handle) + blank `guidelines.md` (edited in dashboard, untouched by update-channel). Edit: `update-channel --slug <slug> [--platform] [--handle] [--name] [--bio]`.
- **Product**: `create-product --project <project-slug> --slug <slug> --name "<Name>" --type app|physical|service --status idea|building|live|paused|archived`. Creates `product.md` (name/type/status) + seeded `roadmap.md` (see product-build skill). No `update-product` yet — for a rename/status change, tell the user it's a manual edit until one exists; don't hand-write the whole file, just flag the gap.

## Write gate
Propose the entity list (project/profile/channel/product + fields) in chat.
Commit via the matching `create-*`/`update-*` command above only after user
approves — one entity per approval when scaffolding several at once.

## Slug-consistency check (run after every scaffold)
After creating or updating folders, validate:
- Every `project:` reference in a profile.md matches an existing `projects/<slug>/` folder.
- Every `entity` slug in `portfolio/milestones.json` matches an existing project, profile, channel, or product folder.
- Report a `[SLUG MISMATCH]` block for each unresolved reference. Never auto-rename — surface and let the user confirm.

## Rules
- Every new project/profile/product/channel triggers a portfolio-map scaffold run.
- Never delete folders. Archiving via `status: archived` only exists for projects
  today (`update-project --status archived`) — `profile.md`/`channel.md` have no
  `status` field and `product.md`'s can only be set at `create-product` time (no
  `update-product` yet). For profiles/channels/products, note the entity as
  inactive in chat and flag the missing update path rather than hand-editing the
  frontmatter to add a field the schema doesn't support.
- Slugs are immutable identifiers: lowercase-kebab, never reused after archiving.
- After scaffolding, recommend running portfolio-timeline to rebuild the unified view.
