# OS Restructure — Project · Profile · Channel · Product

**Date:** 2026-06-17
**Status:** Design (approved for planning)
**Context:** The OS data model used three competing top-level types (`venture`,
`brand`, `project`) and a confusingly overloaded word "channel" (it meant both
*the brand entity* in `db.py` and *a platform list* in `relationships.md`; the
dashboard called the same thing a "Social profile"). The seed data has been
wiped (`4ddf2d4`), so this is a clean rebuild with **no migration**.

---

## 1. Goal

Replace the entity model and its nomenclature with one clear hierarchy, and make
the filesystem layout the source of the hierarchy so it is easy to author by hand.

Every concept gets exactly one word:

> **Project · Profile · Channel · Product · Post**

---

## 2. Entity model

Five entity types (was: `venture`, `project`, `brand`, `web_app`, `external`):

| Type | What it is | Nests under | Multiplicity |
|---|---|---|---|
| **project** | The single top-level container. Was venture **and** brand **and** project. | — (root) | many |
| **profile** | A content presence with its own topic + voice (e.g. Demo, Sample). | project | 0..n per project |
| **channel** | A profile's account on one platform (TikTok, Instagram, YouTube, newsletter…). | profile | 0..n per profile |
| **product** | Something the project builds/sells. Generic — an app, a physical product, a service. Not assumed to be software. | project | 0..n per project |
| **external** | An outside stakeholder or dated event with no parent (kept as-is). | — | — |

### Project "kind"
A project is a *venture* or a *brand* only by **which modules it has**, not by a
different type:
- **Strategy module** present → it behaves like a venture (problem-validation,
  GTM, positioning, pricing, experiments).
- **Product(s)** present → it ships something.
- A project with neither is "just a set of profiles" — a content brand.

An optional `kind: venture | brand` label is stored for the dashboard badge;
when absent it is inferred (has strategy or products ⇒ venture, else brand).

### Relationships
Only `belongs_to` edges, all derived from folder nesting:
`profile → project`, `channel → profile`, `product → project`.
(The `relationships` table keeps its shape but the indexer emits only
`belongs_to`. `drives_to` / `depends_on` are dropped from use for now.)

---

## 3. Content model

- A **Post** is authored once at the **Profile** level — shared body (hook,
  caption, visual brief, pillar, idea).
- It **targets one or more Channels**. Each target may carry an **optional
  per-channel override** (a variant body) when that platform's version differs;
  otherwise the channel inherits the shared body.
- **One stage + one date per post**, shared across its channels:
  Idea → Draft → Scheduled → Published. Different per-channel scheduling is
  **deferred** (YAGNI). The existing internal status enum and the plain-stage
  mapping (`plainStatus`) from dashboard Phase 2 are retained.

---

## 4. Voice cascade

Generation inherits identity top-down:

> **Project voice → Profile voice → Channel guidelines**

A Demo-on-TikTok post composes Acme's overall voice + Demo's
cinema topic/voice + TikTok's per-platform posting rules. This replaces today's
single flat "brand identity" injection.

---

## 5. Filesystem **is** the hierarchy

The central `portfolio/relationships.md` graph file is **removed**. Folder
nesting defines parent/child; each entity carries a small frontmatter metadata
file. The indexer walks the tree and derives entities + `belongs_to` edges.

```
projects/<project-slug>/
   project.md                      # frontmatter: name, kind?, priority, hours_per_week, status
                                   # body: overall voice / identity
   strategy/                       # optional (venture)
      intake.md                    # venture facts + ## Evidence log
      memos/<type>-vN.json         # problem-validation, assessment, positioning, pricing…
      experiments/<id>.json
   products/<product-slug>/        # optional, 0..n
      product.md                   # frontmatter: name, type (app|physical|service|other), status
      roadmap.md                   # features + micro-features (markdown checklist)
   profiles/<profile-slug>/        # 0..n
      profile.md                   # frontmatter: name, topic;  body: profile voice
      content/
         plan-<period>.json        # posts: shared body + target channels + optional overrides
         briefs/<post-id>.json
      channels/<channel-slug>/     # 0..n
         channel.md                # frontmatter: platform;  body: per-platform guidelines

portfolio/                          # cross-project, unchanged
   activities.md                    # manual non-GTM checklist
   milestones.json                  # manual dated events
```

### Entity metadata files (frontmatter shape)
- `project.md` — `name`, `kind?` (venture|brand), `priority` (primary|secondary),
  `status`, `hours_per_week`. Body = overall voice.
- `product.md` — `name`, `type` (app|physical|service|other), `status`.
- `profile.md` — `name`, `topic`. Body = profile voice.
- `channel.md` — `platform`. Body = per-platform posting guidelines.

### Channel slugs
Entity slugs are global primary keys, so a channel's slug must be globally
unique — it is the channel folder name and is **`<profile>-<platform>`** by
convention (e.g. `demo-tiktok`), not a bare platform name. `channel.md`
still carries the bare `platform: tiktok` in frontmatter for grouping/icons.

### Post / plan JSON shape (per item)
```json
{
  "id": "post-001",
  "date": "2026-07-01",
  "pillar": "…",
  "status": "planned",
  "hook": "…", "caption": "…",
  "channels": ["demo-tiktok", "demo-instagram"],   // target channel slugs
  "overrides": { "demo-instagram": { "caption": "…" } }      // optional, keyed by channel slug
}
```
The `briefs/<post-id>.json` holds the expanded content (visual brief + genai
prompt), still shared with optional per-channel overrides keyed by channel slug.

---

## 6. Database (derived index) changes

`os.db` stays a disposable read-only index, rebuilt from files. Changes:

- `entities.type` CHECK → `('project','profile','channel','product','external')`.
- Add `entities.subtype` (nullable) to hold project `kind` and product `type`
  for the dashboard.
- `posts`: rename `brand_slug` → `profile_slug` (REFERENCES `entities`). Add a
  `post_channels(post_id, channel_slug)` join table for targeting; the index on
  `(profile_slug, date)` replaces `idx_posts_brand_date`.
- `features.entity_slug` now references a **product** entity.
- `memos` / `experiments` `entity_slug` reference the **project** (strategy is
  project-level).
- `timeline` VIEW updated: posts join through `profile_slug`; `kind` values
  (`post`/`experiment`/`feature`/`activity`/`milestone`) unchanged.
- `milestones.entity_type` comment updated to the new types.

---

## 7. Indexer (`index.py`)

Replace the `relationships.md` parser with a **tree walk**:
1. `projects/*/project.md` → project entity (subtype = kind).
2. `projects/*/strategy/` → memos, experiments, intake (entity = project).
3. `projects/*/products/*/product.md` → product entity `belongs_to` project;
   `roadmap.md` → features (entity = product).
4. `projects/*/profiles/*/profile.md` → profile entity `belongs_to` project;
   `content/plan-*.json` + `briefs/` → posts (`profile_slug`); each post's
   `channels` → `post_channels` rows.
5. `projects/*/profiles/*/channels/*/channel.md` → channel entity `belongs_to`
   profile.
6. `portfolio/activities.md`, `portfolio/milestones.json` → unchanged.

Keep the existing guarantees: wipe + rebuild, entities before edges, fail loudly
on a `belongs_to` target that does not resolve, tolerate missing folders
(empty workspace → empty db).

---

## 8. Dashboard (`dashboard/app.html`, `db.py`, `fileops.py`)

### Read layer (`db.py`)
- `tree()` returns projects with nested **profiles** (each with its channels) and
  **products**; rename the internal "channels"/"brands" wording to
  profiles/channels correctly.
- `project(slug)` returns the project's sections data (strategy memos,
  experiments, products, profiles).
- `profile_posts(slug)` (was `channel_posts`) returns a profile's posts with
  their target channels.
- `channel(slug)` returns a channel's guidelines.

### Write layer (`fileops.py`)
- Post CRUD writes to `…/profiles/<slug>/content/…`; `profile_slug` + `channels`
  list; plan wrapper unchanged in spirit. Re-index after every mutation.
- Guidelines read/write target `channel.md` per-platform.

### Rail
```
Across everything   →  Needs you · Operations · Calendar
Projects
  └─ <Project>  (badge: venture | brand)
       Sections: Overview · Problem & validation · Experiments
                 Positioning & pricing · Product · Operations
       Profiles:
         └─ <Profile>  → content board (its posts; each shows target channels; filter by channel)
              Channels: <channel> → guidelines page
```
Content board is at the **Profile** level (posts are profile-level); channels are
shown as post targets / filters and each has a guidelines page. The Product
section lists the project's product(s), each with its roadmap.

---

## 9. Nomenclature sweep (apply everywhere)

| Old | New | Where |
|---|---|---|
| `type` `venture`/`brand`/`project` | `project` (+ `subtype` kind) | schema, index.py, dashboard |
| "brand" (content presence) | **profile** | schema, index.py, db.py, dashboard, skills |
| db `brands()` / `channel_posts()` / tree "channels" | **profiles** / `profile_posts` / **channels** | db.py |
| "channel" meaning the brand | dropped | db.py, dashboard |
| "channel" meaning platform list | **channel** (first-class entity) | schema, index.py |
| UI "Social profile" | **profile** | app.html |
| `web_app` / "app" | **product** (generic) | schema, index.py, dashboard, skills |
| `posts.brand_slug` | `posts.profile_slug` + `post_channels` | schema, fileops, db |
| skills: brand-identity, channel-strategy, venture-intake, product-build, portfolio-map, etc. | project/profile/channel/product language | skills/*, README, templates, docs/guide.md |

Result: one word per concept across schema, code, UI, skills, and docs.

---

## 10. Out of scope (later phases)

- Per-channel independent scheduling/stages.
- The live Consultant (advise + propose→apply) and a real cross-project
  Needs-you / Operations.
- Reworking the content-pipeline status enum itself (kept; only the entity it
  hangs off changes).
- Multiple products sharing features, or cross-project dependencies.

---

## 11. Build sequence (subagent-driven, tests per step)

1. **Schema** — new migration: entity types, `subtype`, `posts.profile_slug`,
   `post_channels`, `features`→product, updated `timeline` VIEW.
2. **Indexer** — tree-walk parser; fail-loud FK guard; empty-workspace tolerance.
3. **db.py** — read layer renamed/reshaped (tree, project, profile_posts, channel).
4. **fileops.py** — post CRUD + guidelines against the new paths; reindex wrapper.
5. **Dashboard** — rail (profiles + channels + products), project sections,
   profile content board with channel targets/filters, channel guidelines page.
6. **Skills + docs** — nomenclature pass across the 18 skills, `README.md`,
   `templates/`, `docs/guide.md`; `portfolio-map` reduced to folder scaffolding.

Each step behind unit tests; the dashboard step is smoke-tested (no paid
`/plan` `/brief` calls).

---

## 12. Invariant (unchanged)

Authored files are the source of truth; `database/data/os.db` is a derived,
read-only index opened `mode=ro` by the dashboard and never written by it. Every
change mutates a FILE via `fileops.py`, then re-runs `index.py`. Stdlib-only
Python + single vanilla-JS `dashboard/app.html`. No new dependencies.
