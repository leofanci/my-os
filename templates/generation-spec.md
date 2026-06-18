# Generation Spec — Content Planning Pipeline

> Defines the contract between your system and `claude -p` jobs.
> Two job types: **Plan** (calendar-level) and **Brief** (post-level).
> Everything is JSON so the dashboard and (later) media-gen tools can consume it.

---

## Job 1: PLAN — generate a content calendar

### Input (assembled by your system into the prompt)

The user message contains the VOICE CASCADE:
```
projects/<project-slug>/project.md        ← project voice (overall context)
+ projects/<project-slug>/profiles/<profile-slug>/profile.md  ← profile voice
+ profiles/<profile-slug>/channels/<channel-slug>/guidelines.md  ← per-channel rules
+ parameters:
  - period: e.g., "2026-06-15 to 2026-06-28"
  - platforms: ["instagram", "tiktok", "x", "linkedin"]
  - cadence: posts per platform per week
  - focus: optional ("push the new product", "lean on Pillar 2")
  - history: titles+pillars of last 20 approved posts (avoid repetition)
```

### Output schema

```json
{
  "period": "2026-06-15/2026-06-28",
  "profile": "profile-slug",
  "strategy_note": "1-2 sentences: the angle for this period and why",
  "posts": [
    {
      "id": "draft-001",
      "date": "2026-06-15",
      "channels": ["<channel-slug>"],
      "platform": "instagram",
      "pillar": "Pillar name (must match profile.md)",
      "objective": "awareness | engagement | conversion | community | authority",
      "working_title": "short internal label",
      "concept": "2-3 sentences: what this post does and why now"
    }
  ]
}
```

The Plan output is a calendar skeleton — cheap to generate, easy to review.
You approve/edit/delete slots in the dashboard, THEN trigger Brief jobs
only for approved slots. (Don't generate 30 full briefs you'll throw away.)

---

## Job 2: BRIEF — expand one approved slot into a full content brief

### Input

```
VOICE CASCADE (same as Plan, but filtered to the relevant channel):
  project.md + profile.md + channel guidelines for the targeted channel
+ the approved plan slot (JSON above)
+ platform constraints (char limits, format norms — static config file)
```

### Output schema

```json
{
  "id": "draft-001",
  "channels": ["<channel-slug>"],
  "platform": "instagram",
  "format": "reel | carousel | single_image | text | thread | short | story",
  "objective": "engagement",
  "pillar": "Pillar name",
  "hook": "the first line / first 2 seconds — the scroll-stopper",
  "structure": [
    "beat 1: ...",
    "beat 2: ...",
    "beat 3: ..."
  ],
  "caption": "full ready-to-post caption text",
  "cta": "exact CTA line (must be from allowed CTAs in profile voice)",
  "hashtags": ["..."],
  "visual_brief": {
    "description": "what the visual shows, scene by scene if video",
    "mood": "from profile.md visual mood",
    "format_specs": "9:16 video ~30s | 4:5 carousel 5 slides | etc.",
    "text_overlays": ["overlay 1", "overlay 2"],
    "genai_prompt_draft": "a first-pass prompt for a future image/video gen tool"
  },
  "notes_for_human": "anything Claude flags: needs fact-check, needs real photo, etc."
}
```

`visual_brief.genai_prompt_draft` is the future hook for Midjourney/Runway/etc.
Today it's documentation for you; later a tool consumes it directly.

---

## Pipeline rules

1. **Prompt = voice cascade + task + schema.** The job prompt instructs:
   "Respond ONLY with valid JSON matching this schema. No markdown fences."
2. **Validate before storing.** Parse the JSON; if invalid, retry once with
   the parse error appended. If it fails twice, mark the job failed.
3. **Statuses:** `planned → approved_slot → briefed → approved → scheduled → published`
   (and `rejected` at any review point). Edits in the dashboard create a new
   version, never overwrite — keeps a history of what you changed, which
   later becomes feedback for improving prompts.
4. **History injection:** every Plan job receives recent approved posts so
   the calendar doesn't repeat itself.
5. **One profile per job.** Never mix profile contexts in a single claude -p call.

---

## Storage — local SQLite (no server)

Local SQLite file (`os.db`). No MySQL/Postgres server — they add ops overhead
with no local benefit. SQLite gives full SQL, Claude can query it via the
`sqlite3` CLI, and migration to Postgres/PocketBase later is trivial.

**Hybrid rule:** authored prose stays in files (`profile.md`, briefs as JSON);
SQLite holds only the derived/coordination data that benefits from queries.

```sql
-- content pipeline (one row per post, edits bump version, never overwrite)
CREATE TABLE posts (
  id           TEXT PRIMARY KEY,
  profile_slug TEXT NOT NULL REFERENCES entities(slug),
  date         TEXT,
  channels     TEXT,  -- JSON array of channel slugs
  platform     TEXT,
  pillar       TEXT,
  status       TEXT NOT NULL CHECK (status IN
                 ('planned','approved_slot','briefed','approved',
                  'scheduled','published','rejected')),
  version      INTEGER NOT NULL DEFAULT 1,
  brief_path   TEXT                              -- pointer to the brief JSON file
);
CREATE INDEX idx_posts_profile_date ON posts(profile_slug, date);

-- batch jobs (only needed once you automate plan/brief generation)
CREATE TABLE jobs (
  id         INTEGER PRIMARY KEY,
  type       TEXT NOT NULL CHECK (type IN ('plan','brief')),
  post_id    TEXT REFERENCES posts(id),
  status     TEXT NOT NULL CHECK (status IN ('queued','running','done','failed')),
  error      TEXT,
  created_at TEXT NOT NULL
);
```

`entities` (projects, profiles, products, channels, etc.) is defined once in the
GTM layer spec — posts reference it rather than duplicating profile rows.

---

## CLI invocation pattern (verified, Claude Code 2.1+)

There is **no `--append` flag**. The voice cascade is content, not a system
prompt, so pipe it as the user turn via stdin and put the task/schema in the prompt:

```bash
python3 generate.py plan <profile-slug> \
  --period "2026-06-15 to 2026-06-28" \
  --platforms instagram,x \
  --workspace /path/to/my-portfolio
```

`generate.py` assembles the voice cascade automatically by walking the
`projects/*/profiles/<profile-slug>/` folder tree. Validate the JSON before
storing (see Pipeline rule 2).
