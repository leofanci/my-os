# GTM OS — Claude Code Skills (v2)

A 21-skill operating system for running a portfolio of projects, products, profiles,
and social channels from Claude Code — problem validation, GTM strategy, product
roadmaps, and manual activity tracking, organized in layers.

Every strategic skill behaves like a senior consultant:
options → pros/cons → one recommendation → what would change it.

---

## Workspace structure

```
my-portfolio/
├── CLAUDE.md                   ← auto-loaded context (copy from templates/workspace-CLAUDE.md)
├── os.db                       ← derived SQLite index (disposable; rebuilt from files)
├── portfolio/
│   ├── milestones.json         ← manually entered dates/events (copy from template)
│   ├── activities.md           ← manual non-GTM tasks/micro-items (checklist you tick off)
│   └── timeline-<date>.json    ← unified timeline (generated, rebuilt on demand)
└── projects/
    └── <project-slug>/
        ├── project.md          ← frontmatter: name, kind (venture|brand), priority,
        │                          hours_per_week, status; body = overall project voice
        ├── strategy/           ← (venture projects only)
        │   ├── intake.md       ← venture facts + evidence log
        │   ├── memos/          ← problem-validation, assessment, channels, positioning, pricing, launch
        │   └── experiments/    ← designs + results
        ├── products/           ← 0..n generic products (app|physical|service)
        │   └── <product-slug>/
        │       ├── product.md  ← frontmatter: name, type, status
        │       └── roadmap.md  ← features + micro-features (checklist, hand-edited)
        └── profiles/           ← content presences with their own topic + voice
            └── <profile-slug>/
                ├── profile.md  ← frontmatter: name, topic; body = profile voice
                ├── content/
                │   ├── plan-<period>.json
                │   └── briefs/
                └── channels/   ← per-platform accounts
                    └── <channel-slug>/
                        ├── channel.md      ← frontmatter: platform; body = per-platform notes
                        └── guidelines.md   ← per-channel posting guidelines
```

**Voice cascade** (injected into every content job):
`project.md` body → `profile.md` body → `channels/<slug>/guidelines.md`

---

## Install

```bash
# Copy skills into Claude Code
cp -r skills/* ~/.claude/skills/

# Set up your workspace
mkdir -p my-portfolio/{portfolio,projects}
cp templates/milestones-template.json my-portfolio/portfolio/milestones.json
cp templates/workspace-CLAUDE.md my-portfolio/CLAUDE.md   # auto-loaded operating context

# Start
cd my-portfolio && claude
```

---

## The 21 skills

### Layer 0 — OS dispatcher
| Skill | What it does |
|---|---|
| `gtm-os` | Master dispatcher: routing table, file conventions, hard rules |

### Layer 1 — Portfolio (cross-entity coordination)
| Skill | What it does |
|---|---|
| `portfolio-map` | Scaffold the project/profile/product/channel folder structure |
| `portfolio-timeline` | Build the unified timeline across all entities (queries `os.db`) |
| `portfolio-sync` | Surface this week's cross-entity coordination actions |

### Layer 2 — Project / GTM brain (per-project, kind=venture)
| Skill | What it does |
|---|---|
| `problem-validation` | Validate the problem is real before any build/GTM (full or quick) |
| `venture-intake` | Interview → strategy/intake.md with evidence log |
| `gtm-assessment` | ICP hypotheses, positioning options, pace call |
| `channel-strategy` | Channel comparison, entry strategy, social mandate |
| `experiment-design` | Cheapest test, success/kill criteria |
| `experiment-review` | Log results, persist/pivot/kill |
| `icp-research` | Segment memo, where to find 10 this week, interview guide |
| `positioning` | Category framing, differentiation, messaging hierarchy |
| `competitor-scan` | Landscape map, gaps, how to play it |
| `pricing-strategy` | Model + price point options, price-as-test |
| `launch-plan` | Soft vs loud, sequencing, assets, failure plan |

### Layer 2b — Product (per product, generic: app|physical|service)
| Skill | What it does |
|---|---|
| `product-build` | Roadmap, feature planning, manual micro-features, releases → content ramp |

> Manual micro-features and non-GTM tasks: add them by hand to
> `products/<slug>/roadmap.md` or `portfolio/activities.md` (markdown checklists)
> and tick them off — no skill needed; the timeline picks them up.

### Layer 3 — Profile & content (per profile)
| Skill | What it does |
|---|---|
| `brand-identity` | Create/refresh profile.md and channel guidelines from interview or project mandate |
| `content-plan` | Calendar skeleton with channel targets (approve before expanding) |
| `content-brief` | Full briefs with visual brief + genai prompt draft |
| `copy-variants` | Cross-channel adaptation, hook batches, A/B pairs |

### Layer 4 — Operating cadence
| Skill | What it does |
|---|---|
| `weekly-review` | Per-project snapshot + priorities (queries `os.db`) |
| `portfolio-sync` | Cross-entity coordination actions for this week |

---

## The full loop

```
SETUP
  portfolio-map → scaffold projects/<slug>/ structure

PER PROJECT (kind=venture)
  problem-validation → is the problem real? (gates the pace call)
  venture-intake → strategy/intake.md
  gtm-assessment → memo: ICP + pace call
  channel-strategy → memo: primary channel + social mandate
  experiment-design → design file (run the test)
  experiment-review → result logged to intake evidence
  [assessment rerun when evidence changes]

PER PRODUCT (app|physical|service)
  product-build → products/<slug>/roadmap.md (features, micro-features, releases)
  [a release triggers a content ramp on linked profiles]

PER PROFILE (may be triggered by channel-strategy social mandate)
  brand-identity → profile.md + channel guidelines
  content-plan → skeleton (you approve slots)
  content-brief → full briefs for approved slots → scheduler

COORDINATION (all query os.db, the derived index)
  portfolio-timeline → unified view rebuilt after any major change
  portfolio-sync → cross-entity actions this week
  weekly-review → per-project priorities

FUTURE (plugs into visual_brief.genai_prompt_draft)
  → image gen tool (Midjourney / Ideogram / Flux)
  → video gen tool (Runway / Kling / Hailuo)
```

---

## First session

```
1. "Set up the portfolio structure"             → portfolio-map
2. "Is [idea] worth doing?"                     → problem-validation
3. "Intake for [your first project]"            → venture-intake
4. "GTM assessment for [project]"               → gtm-assessment
5. React to the memo. Push back.
6. "Design an experiment for the riskiest assumption"  → experiment-design
7. (Later) "Build the unified timeline"         → portfolio-timeline
```

---

## Design principles

- **Decision memos, not plans**: every strategic output gives options, not one answer.
- **Evidence-driven**: pace calls, recommendations, and ICP confidence are tied to
  logged evidence — not vibes.
- **Timeline is derived**: coordination skills query `os.db`, a disposable SQLite
  index rebuilt from the source files; source files always win. Rebuild after any
  significant update.
- **Manual layers are hand-edited files**: `milestones.json` (fixed dates — releases,
  investor meetings, deadlines) and `activities.md` / `products/<slug>/roadmap.md`
  (tasks and micro-features you tick off). Things no skill knows unless you tell it.
- **Skills improve like docs**: when output feels off, edit the SKILL.md.
  The OS gets better permanently.
