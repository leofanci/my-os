# Multiple brief-specs and voices per profile — design

**Date:** 2026-07-09
**Scope:** A profile currently has exactly one brief-spec and one voice. Let a profile hold several of each, each optionally scoped to a subset of the profile's platforms (or "all"), selected manually wherever generation happens — dashboard buttons, chat, and manual editing, via the same underlying commands.

## Problem

`profiles/<slug>/brief-spec.md` (core/brief_spec_util.py) and `profile.md`'s body (voice, read via `dashboard/fileops.py:read_profile`) are each a single file. The ID registry hardcodes exactly one of each: `pf.sec01.br1` and `pf.sec01.vc1` (core/ids.py, `IdRegistry.build`, ~line 484-490). There's no way to have a second brief-spec (e.g. a TikTok-specific one) or a second voice without overwriting the only one that exists.

Not in scope: automatic platform-matching or layered/merged specs. Selection is always a manual, explicit choice — the platform tag on a brief/voice is a label for the human, not a rule the system applies for them.

## Current behavior (what already exists)

- `core.brief_spec_util` — single `brief-spec.md` per profile, "single source of truth" per its own docstring. `read_spec_text`/`write_spec_text` operate on that one file.
- `dashboard/fileops.py:read_profile` — reads `profile.md` frontmatter (name/topic/project) + body (voice) as one string. `read_brief_spec`/`write_brief_spec` — same, one file.
- `core/ids.py` `IdRegistry.build` — for each profile, unconditionally adds `{setup_tab_id}.br1` bound to `lk_prof_brief_spec(slug)` and `{setup_tab_id}.vc1` bound to `lk_prof_voice(slug)`. No loop, no count.
- `generate.py`:
  - `build_voice_cascade(profile_dir, platforms)` — concatenates project voice + profile voice (whole `profile.md` body) + matching channel guidelines. Used by both `do_plan` and `do_brief`.
  - `do_plan` — reads `read_spec_text(profile_dir)` (the one brief-spec) and the voice cascade; takes a single `cadence` int (posts per platform per week).
  - `do_brief` — same one brief-spec, one voice cascade, for a single post.
- `dashboard/app.js` — Profile Setup panel (`ps-voice`, `ps-brief` textareas, ~line 1248-1262) shows exactly one of each; `PUT /api/profile/{slug}/brief-spec` and profile update write the single files.
- `dashboard/ai_rules.py` — `BRIEF_SPEC` const documents `update-brief-spec` / `get-brief-spec` and says "Voice → `update-profile --voice`, not brief-spec."
- A parallel, currently-uncommitted rewrite in `core/ids.py` (not part of this feature, already in the working tree) replaces "recompute id from position" with a persisted registry: `load_id_registry`/`save_id_registry`/`allocate`/`next_counter`, backed by `database/data/id_registry.json`. `next_counter(registry, scope)` mints a brand-new monotonic number with no natural key, for entities (like `mint_post_ids`) whose final composed id is baked into the entity itself once and never re-derived. This feature reuses that mechanism rather than inventing a second numbering scheme.

## Design

### 1. Storage

Per profile:
- `brief-specs/br{N}.md` — one file per brief-spec (named to avoid collision with the existing per-post `content/briefs/{post-id}.json` output dir). Frontmatter `platforms: all` or `platforms: instagram,tiktok` (validated against that profile's actual channel platforms at write time) + body = spec text (same content that used to live in `brief-spec.md`).
- `voices/vc{N}.md` — one file per voice. Same shape: `platforms:` frontmatter + body = voice text (what used to live in `profile.md`'s body).
- `profile.md` keeps only `name`/`topic`/`project` frontmatter; body is no longer the voice (see migration below).

`N` is minted once via `next_counter(registry, f"brief:{profile_slug}")` (or `f"voice:{profile_slug}"`) at creation time and baked straight into the filename — mirrors how `mint_post_ids` bakes a post's final id into the plan JSON. `IdRegistry.build` never re-derives the number: it lists `brief-specs/*.md` / `voices/*.md`, parses `N` from each filename, and uses it as-is. Deleting `br2` never renumbers `br3`; a later new brief becomes `br4` (`next_counter` is monotonic and never reused, same guarantee the registry already gives posts/memos/experiments).

### 2. IDs

`pr1.pf2.sec01.br1`, `br2`, `br3`, … and `sec01.vc1`, `vc2`, … — same `sec01` (Setup tab), just no longer capped at one child of each kind. `get-id-catalog` and `resolve-id` list all of them, same as any other multi-child section (e.g. `pr.secNN.mm*`).

### 3. Selection — always manual, no auto-matching

- The `platforms` tag is informational only (drives a filter/label in dropdowns), never used to auto-pick or auto-merge a spec/voice at generation time.
- Default when nothing is specified: `br1` / `vc1`.
- Each post stores `brief_id` / `voice_id` fields (new slot metadata, same tier as the existing `platform`/`format` fields — no `fd##` id needed, per ID rule #6). Set at plan time (default `br1`/`vc1` unless told otherwise); regenerating a post reuses its stored pair unless overridden. This is the one piece of state that makes "which brief made this post" answerable later.

### 4. Commands (osctl) — symmetric brief/voice

| Action | Brief | Voice |
|---|---|---|
| Create | `create-brief-spec --profile <slug> [--platforms all\|ig,tiktok] --text/stdin` | `create-voice --profile <slug> [--platforms ...] --text/stdin` |
| Update | `update-brief-spec --profile <slug> [--id br2] [--platforms ...] --text/stdin` (id optional, defaults `br1`) | `update-voice --profile <slug> [--id vc2] [--platforms ...] --text/stdin` (defaults `vc1`) |
| Delete | `delete-brief-spec --profile <slug> --id br2` (rejected if it's the only brief left) | `delete-voice --profile <slug> --id vc2` (same guard) |
| Read | `get-brief-spec --profile <slug> [--id br2]` (omit `--id` → all) | `get-voice --profile <slug> [--id vc2]` (omit → all) |

`update-profile --voice` (the current special-cased path) is removed; voice becomes its own symmetric command set instead of living inside profile identity fields. Existing callers (dashboard, chat, `dashboard/ai_rules.py`) move to `create-voice`/`update-voice`.

### 5. Post-level generation (`generate.py do_brief`, dashboard "Write" button, chat)

- `generate-brief --id <post-id> [--spec br2] [--voice vc2]` — omitted flags fall back to the post's stored `brief_id`/`voice_id`, which falls back to `br1`/`vc1` if the post has none yet.
- `build_voice_cascade` gains a `voice_id` param (default `vc1`) and reads `voices/vc{id}.md` instead of `profile.md`'s body for the "PROFILE VOICE" section; everything else (project voice, channel guidelines) is unchanged.
- `read_spec_text`/`format_for_brief_prompt` take a `brief_id` param (default `br1`) and read `brief-specs/br{id}.md`.
- Chat: "generate this post's brief using br2" resolves in the same way a user would type `--spec br2` — no separate code path from the terminal/manual one.

### 6. Bulk plan generation (`generate.py do_plan`, `generate-plan`, the "how many posts/week" flow)

- Single brief and single voice (the common case, and every profile until the user adds a second): behavior is unchanged, still just `--cadence`.
- Multiple briefs and/or voices exist: the flow additionally asks for a count per brief-id (and per voice-id, if more than one voice exists) — e.g. "5 posts br1, 2 posts br2" — same shape as the existing per-platform cadence prompt, just one more axis. Each minted post gets its `brief_id`/`voice_id` slot fields set according to which group it was minted in.

### 7. Dashboard (Profile Setup panel)

- The single `ps-voice` / `ps-brief` textareas become repeatable rows: platform-tag chip (dropdown built from that profile's channel platforms, plus "all") + textarea + delete button, with a `+ Add brief` / `+ Add voice` button per section.
- Post editor (wherever `platform`/`format` are already editable per slot) gains `brief_id`/`voice_id` selectors, only shown when a profile has more than one of either — no extra UI clutter for the common single-brief case.

### 8. Migration

One-time, on first read of a profile that hasn't been migrated (detected by the absence of `brief-specs/`/`voices/` dirs):
- `brief-spec.md` (if present) → `brief-specs/br1.md`, `platforms: all`.
- `profile.md` body (if non-empty) → `voices/vc1.md`, `platforms: all`.
- `profile.md` is rewritten to keep only its frontmatter, empty body.
- Existing posts get no retroactive `brief_id`/`voice_id` (they predate the concept); reads default to `br1`/`vc1` for posts missing the field, same as the global default.

## Decisions

- **Manual selection only** — confirmed with the user; no platform auto-matching, no layered merge. Keeps the mental model to "pick one," not "reason about precedence."
- **Numbering via `next_counter`, baked into the filename** — reuses the persisted-registry mechanism already being introduced elsewhere in `core/ids.py` for exactly this "mint once, never re-derive" shape, instead of a second scanning-based scheme (like `next_memo_version`'s glob-and-regex approach).
- **`platforms` validated against the profile's real channels** — so the dropdown in the dashboard is a real list, not free text that can drift from what channels actually exist.
- **Post tracks `brief_id`/`voice_id`** — confirmed with the user; makes "what produced this post" inspectable and regeneration deterministic by default.
- **`update-profile --voice` removed, not kept as a shim** — voice is no longer a profile identity field; keeping the old flag pointing at `vc1` would mean two ways to edit the same thing forever. `create-voice`/`update-voice` fully replace it.

## Affected files

- `core/ids.py` — `IdRegistry.build`: loop over `brief-specs/`/`voices/` dirs instead of hardcoding `br1`/`vc1`; new `create_brief_id`/`create_voice_id` helpers using `next_counter`.
- `core/brief_spec_util.py` — `spec_file`/`read_spec_text`/`write_spec_text` take a `brief_id` param; platform frontmatter parse/validate.
- New `core/voice_util.py` (mirrors `brief_spec_util.py`) for voice file read/write/validate — keeps brief and voice symmetric at the code level too.
- `dashboard/fileops.py` — `read_profile`/`update_profile` drop voice; new `create_brief_spec`/`update_brief_spec`/`delete_brief_spec`/`create_voice`/`update_voice`/`delete_voice`/`list_briefs`/`list_voices`.
- `dashboard/server.py` — routes for the six new/changed commands, symmetric brief/voice.
- `generate.py` — `build_voice_cascade`, `do_plan`, `do_brief` gain `brief_id`/`voice_id` params; `do_plan` prompts for per-brief/per-voice counts when >1 exists.
- `dashboard/app.js` — Profile Setup panel repeatable rows; post editor brief/voice selectors (conditional on >1 existing).
- `dashboard/ai_rules.py` — `BRIEF_SPEC` const rewritten for the new command table; drop the `update-profile --voice` note.
- `core/ids.py` migration helper (or a small standalone migration function) for the one-time `brief-spec.md`/`profile.md` body → `brief-specs/br1.md`/`voices/vc1.md` move.

## Tests

- Migration: legacy profile (only `brief-spec.md` + `profile.md` body) reads as `br1`/`vc1` after first touch; idempotent on second run.
- ID registry: profile with 3 briefs / 2 voices gets `br1..br3`/`vc1..vc2`; deleting `br2` then adding a new one yields `br4`, not a reused `br2`.
- `platforms` validation: rejects a platform not present in the profile's channels; accepts `all`.
- `create-brief-spec`/`update-brief-spec`/`delete-brief-spec` and the voice equivalents — round-trip content, delete-guard on last remaining one.
- `do_brief`/`generate-brief`: explicit `--spec`/`--voice` picks the right file; omitted falls back to the post's stored ids, then to `br1`/`vc1`.
- `do_plan`: single brief/voice → unchanged behavior; multiple → per-group counts produce posts with correct `brief_id`/`voice_id` slot fields.
- Dashboard: Profile Setup add/delete rows; post editor selectors only render when >1 brief or voice exists.
