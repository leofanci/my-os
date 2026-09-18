# Project / GTM Layer — Intake Template & Job Spec

> One folder per project: `projects/<project-slug>/`
> Strategy (venture kind) sits inside `strategy/`. Profiles (content presences)
> and products live as siblings. Standalone brand profiles skip the strategy layer entirely.

---

# PART 1 — Project Intake (`projects/<slug>/strategy/intake.md`)

> Filled by you. Injected into every strategy job for this project.
> Honest answers > impressive answers. The brain is only as good as this file.

## 1. What it is

- **Project name:**
- **One-liner:** (what it does, for whom)
- **Problem it solves:** (in the customer's words, not yours)
- **Current solution people use instead:** (competitor, spreadsheet, "nothing")
- **Why now:** (what changed in the world that makes this viable)

## 2. Stage & evidence

- **Stage:** idea / prototype / live product / revenue
- **Evidence so far:** (signups, interviews done, sales, waitlist — numbers, even if small or zero)
- **Strongest validated assumption:**
- **Riskiest UNvalidated assumption:** (if you don't know, say so — the brain will propose candidates)

## 3. Market

- **Who you THINK the customer is:** (best current guess at ICP)
- **Who actually pays vs. who uses:** (if different)
- **Market type:** new category / existing category, new angle / cheaper-better clone
- **Geography / language:**
- **Price point (current or intended):**

## 4. Resources & constraints

- **Time available:** (hrs/week you can give this project)
- **Budget for GTM testing:** (monthly, even if ~0)
- **Team:** (solo / who else, what skills)
- **Unfair advantages:** (audience, network, domain expertise, distribution access)
- **Hard constraints:** (regulatory, platform dependency, runway deadline)

## 5. Goals & risk posture

- **6-month definition of success:** (specific: "20 paying customers", "validated ICP", "1k waitlist")
- **Risk appetite:** cautious / balanced / aggressive
- **What would make you kill this project:** (your own kill criteria)

## 6. Portfolio context

- **Other projects competing for your time:**
- **Priority of this one:** primary / secondary / experiment

---

# PART 2 — Strategy Jobs (the GTM brain's outputs)

> Same pipeline mechanics as content: `claude -p` + intake.md + schema → JSON → dashboard.
> Three job types, used in order. Each one is a DECISION MEMO: options, pros/cons,
> recommendation — never a single take-it-or-leave-it plan.

## Job A: GTM ASSESSMENT (run first, rerun when evidence changes)

```json
{
  "project": "slug",
  "date": "2026-06-12",
  "stage_read": "1-2 sentences: where this project actually is",
  "icp_hypotheses": [
    {
      "segment": "who",
      "why_them": "...",
      "confidence": "low | medium | high",
      "evidence_basis": "what in the intake supports this"
    }
  ],
  "positioning_options": [
    { "angle": "...", "pros": ["..."], "cons": ["..."] }
  ],
  "pace_recommendation": {
    "call": "validate_quietly | soft_launch | accelerate",
    "reasoning": "why, tied to riskiest assumption and resources",
    "what_would_change_this": "evidence that would flip the call"
  },
  "riskiest_assumptions_ranked": ["1...", "2...", "3..."],
  "recommendation": "the single path the consultant would take, and why"
}
```

## Job B: CHANNEL & ENTRY STRATEGY (after you approve an ICP + pace)

```json
{
  "project": "slug",
  "approved_icp": "...",
  "channel_options": [
    {
      "channel": "social_organic | outreach | community | paid | partnerships | content_seo | product_led",
      "fit_reasoning": "why this channel for THIS icp and THESE resources",
      "pros": ["..."],
      "cons": ["..."],
      "cost": "time + money estimate",
      "time_to_signal": "how long until you know if it works",
      "verdict": "primary | secondary | not_now"
    }
  ],
  "entry_strategy_options": [
    { "strategy": "e.g., niche-down beachhead vs. broad launch", "pros": [], "cons": [] }
  ],
  "recommendation": "primary channel + entry strategy + why",
  "social_media_mandate": {
    "needed": true,
    "purpose": "what social is FOR in this GTM (discovery? credibility? none?)",
    "brand_brief_seed": "1 paragraph that seeds a new profile.md if needed: positioning, audience, tone direction"
  }
}
```

`social_media_mandate.brand_brief_seed` is the bridge to the profile layer:
approve it, and it pre-fills a new profile voice (profile.md) and channel guidelines.

## Job C: EXPERIMENT DESIGN (the testing brain — repeatable)

```json
{
  "project": "slug",
  "assumption_under_test": "...",
  "experiment_options": [
    {
      "name": "e.g., 10 problem interviews | landing page smoke test | concierge MVP",
      "design": "exactly what to do, step by step",
      "cost": "time + money",
      "success_criteria": "quantified: 'X of Y say Z'",
      "kill_criteria": "result that means stop/pivot",
      "pros": ["..."], "cons": ["..."]
    }
  ],
  "recommendation": "which experiment first and why",
  "duration": "calendar time"
}
```

### The loop that makes it an OS, not a strategy doc

```
strategy/intake.md → [A: Assessment] → you approve ICP + pace
                   → [B: Channels]  → you approve channel plan
                                     → may spawn a profile + content pipeline (layer below)
                   → [C: Experiment] → you RUN it → log result in dashboard
                   → result appended to intake "evidence" → rerun A → strategy updates
```

**Rule: every Job A rerun receives all logged experiment results.** Strategy
that ignores new evidence is theater.

---

# PART 3 — Data layer (local SQLite, hybrid)

Storage is a single local SQLite file (`os.db`) — no server. **Files stay the
source of truth for authored prose** (`strategy/intake.md`, `profile.md`,
`project.md`, the memo/brief JSON). SQLite is the *derived, queryable index* for
coordination: entities, links, statuses, dates, experiment outcomes. The timeline
is a VIEW over it, so "source files win" still holds.

```sql
-- every thing you're growing (unifies projects, profiles, products, channels, external)
CREATE TABLE entities (
  slug       TEXT PRIMARY KEY,
  type       TEXT NOT NULL CHECK (type IN ('project','profile','product','channel','external')),
  name       TEXT NOT NULL,
  priority   TEXT CHECK (priority IN ('primary','secondary','experiment')),
  status     TEXT NOT NULL DEFAULT 'active',
  hours_per_week INTEGER,                        -- from project.md; powers capacity/[CONFLICT] checks
  file_path  TEXT,                              -- project.md / profile.md / roadmap.md (source of truth)
  updated_at TEXT NOT NULL
);

-- typed edges (profile belongs_to project, product drives_to landing page, etc.)
CREATE TABLE relationships (
  from_slug TEXT NOT NULL REFERENCES entities(slug),
  to_slug   TEXT NOT NULL REFERENCES entities(slug),
  kind      TEXT NOT NULL CHECK (kind IN ('belongs_to','drives_to','depends_on')),
  PRIMARY KEY (from_slug, to_slug, kind)
);

-- strategy memos: metadata only; the decision-memo body stays in the JSON file
CREATE TABLE memos (
  id          INTEGER PRIMARY KEY,
  entity_slug TEXT NOT NULL REFERENCES entities(slug),
  type        TEXT NOT NULL CHECK (type IN
                ('problem-validation','assessment','channels','icp',
                 'positioning','competitors','pricing','launch')),
  version     INTEGER NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('proposed','approved','superseded')),
  file_path   TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  UNIQUE (entity_slug, type, version)
);

CREATE TABLE experiments (
  id            INTEGER PRIMARY KEY,
  entity_slug   TEXT NOT NULL REFERENCES entities(slug),
  assumption    TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('planned','running','done')),
  duration_days INTEGER,
  started_on    TEXT,
  decision      TEXT CHECK (decision IN ('persist','pivot','kill')),
  result        TEXT,
  file_path     TEXT
);

-- the THIN non-GTM layer: tracked items with NO strategy skills behind them
CREATE TABLE activities (
  id          INTEGER PRIMARY KEY,
  entity_slug TEXT REFERENCES entities(slug),  -- nullable: standalone tasks allowed
  title       TEXT NOT NULL,
  date        TEXT,
  date_end    TEXT,
  type        TEXT NOT NULL,                    -- release|deadline|investor|event|personal|task
  status      TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','running','blocked','done')),
  priority    TEXT CHECK (priority IN ('critical','high','normal','low'))
);

-- product roadmap features (source of truth: products/<slug>/roadmap.md checklist)
CREATE TABLE features (
  id           INTEGER PRIMARY KEY,
  product_slug TEXT NOT NULL REFERENCES entities(slug),
  title        TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('idea','planned','building','shipped')),
  priority     TEXT CHECK (priority IN ('critical','high','normal','low')),
  target_date  TEXT,
  shipped_date TEXT,
  release      TEXT
);
CREATE INDEX idx_features_product_status ON features(product_slug, status);

-- fixed external/dated events from portfolio/milestones.json (manual, no status)
CREATE TABLE milestones (
  id          TEXT PRIMARY KEY,
  entity_slug TEXT REFERENCES entities(slug),   -- nullable: 'external' events map to no entity
  entity_type TEXT,                              -- project|profile|product|channel|external
  type        TEXT NOT NULL,                     -- release|deadline|investor|partnership|event|personal
  title       TEXT NOT NULL,
  date        TEXT NOT NULL,
  date_end    TEXT,
  priority    TEXT CHECK (priority IN ('critical','high','normal','low')),
  notes       TEXT
);
```

`activities` (your tasks, have status, you tick off) and `milestones` (fixed
external dates, no status) are deliberately separate — they mirror the two
source files `activities.md` and `milestones.json`.

**Source-of-truth files for the new layers** (SQLite only indexes them):
- `products/<slug>/roadmap.md` — product features + micro-features, a markdown
  checklist (`- [ ]` / `- [x]`) you add to and tick off by hand → `features`.
- `portfolio/activities.md` — manual non-GTM tasks/micro-items, same checklist
  style → `activities`.

**Rebuild trigger:** an `index` step (run on demand, or via a `PostToolUse` hook
when a source file changes) wipes and repopulates `os.db` from the files. The DB
is never the source of truth, so a full rebuild is always safe and cheap.

The `timeline` VIEW unions experiments, posts, features (releases), activities,
and milestones — that single VIEW is what the coordination skills query.

Migration path: SQLite → PocketBase (SQLite-backed) or Postgres is mechanical,
since this is standard SQL. Don't add a server until a UI or multi-user need
actually exists.

---

# Build order

The skills (this layer) work file-based today. The full build sequence —
seed data → `claude -p` pipeline ∥ indexer → rebuild hook → dashboard — lives
in `BUILD.md` at the repo root. Build against real files; never ahead of them.
