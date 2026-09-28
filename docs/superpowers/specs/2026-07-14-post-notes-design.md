# Post notes — design

## Problem

The OS tracks content that went through its own pipeline (`Post` records: planned → briefed → approved → published, with a brief/draft/schedule). Sometimes the user posts something on a profile spontaneously, outside that pipeline — it never becomes a `Post` record. Right now there's no trace of that anywhere in the OS: the profile page and the Calendar under-represent what actually went out.

## Goal

A lightweight, manual **post note**: a dated marker attached to a profile saying "I posted something here," with an optional longer note and optional channel tags. Not a `Post` — no brief, no draft, no publish pipeline, no status workflow. Closer to a diary entry than a content artifact.

Requirements:
- Create with **title** (required, short), **date** (required), **text** (optional, longer), **channels** (optional, multi-select from the profile's channels, all pre-checked by default, can uncheck to none).
- Edit later — especially the date (reschedule).
- Delete.
- Visible on the profile page (as a log) and on the global Calendar (alongside posts/milestones/features).

## Data model

New tables in `database/migrations/0001_init.sql` (index.py wipes and rebuilds `os.db` from authored files on every reindex, so this file is edited in place rather than layering a new migration):

```sql
CREATE TABLE post_notes (
  id           TEXT PRIMARY KEY,        -- "pn-xxxxx" stamp, same style as milestones' "ms-xxxxx"
  profile_slug TEXT NOT NULL REFERENCES entities(slug),
  date         TEXT NOT NULL,
  title        TEXT NOT NULL,
  text         TEXT                     -- optional
);
CREATE INDEX idx_post_notes_profile_date ON post_notes(profile_slug, date);

CREATE TABLE post_note_channels (
  post_note_id TEXT NOT NULL REFERENCES post_notes(id),
  channel_slug TEXT NOT NULL REFERENCES entities(slug),
  PRIMARY KEY (post_note_id, channel_slug)
);
```

`post_notes`/`post_note_channels` mirror the existing `posts`/`post_channels` pair exactly, minus the fields that don't apply (pillar, working_title, concept, status, version, brief_path).

### Source of truth

`projects/<project>/profiles/<profile>/post-notes.json` — one file per profile (found via the existing `_profile_dir(slug)` helper in `dashboard/fileops.py`), shape:

```json
{
  "notes": [
    {"id": "pn-a1b2c3", "date": "2026-07-14", "title": "Behind the scenes story",
     "text": "Posted a quick BTS clip, not part of the plan.",
     "channels": ["profile-a-instagram"]}
  ]
}
```

`channels` is an array; empty array or omitted means no channel tagged.

### Timeline

`timeline` view (in the same migration file) gets a new `UNION ALL` branch:

```sql
UNION ALL
  SELECT n.date, NULL, n.profile_slug, 'post_note',
         n.title, NULL, e.priority, e.hours_per_week, n.id
  FROM post_notes n LEFT JOIN entities e ON e.slug = n.profile_slug
```

This makes post notes appear on `/api/timeline` (and therefore the Calendar) automatically, with `kind='post_note'` and `ref_id` pointing at the note for edit/delete.

## Backend

Follows the existing milestone CRUD pattern precisely.

- **`core/ids.py`**: `next_post_note_id(existing)` → `_stamp("pn-", existing)`.
- **`index.py`**: `collect_post_notes(root, slugs)` — globs `projects/*/profiles/*/post-notes.json`, flattens each profile's `notes` list into `post_notes` rows plus `post_note_channels` join rows. Registered in `check_slugs` so a note referencing a channel slug that doesn't exist fails the reindex loudly, same as other entity references.
- **`dashboard/fileops.py`**:
  - `create_post_note(fields)` — requires `profile` (resolves via `_profile_dir`), `title`, `date`. Optional `text`, `channels` (parsed with the existing `_parse_channels` helper, validated against the profile's actual channel slugs). Appends to that profile's `post-notes.json`, calls `reindex()`.
  - `update_post_note(id, fields)` — finds the note by id across profile `post-notes.json` files (same lookup style as `update_milestone` scanning `portfolio/milestones.json`, but globbing profile dirs), patches provided fields, `reindex()`.
  - `delete_post_note(id)` — removes the note, `reindex()`.
- **`dashboard/osctl.py`**:
  - `create-post-note --profile --title --date [--text] [--channels]`
  - `update-post-note --id [--title] [--date] [--text] [--channels]`
  - `delete-post-note --id`
- **`dashboard/server.py`**:
  - `POST /api/post-note/new`
  - `POST /api/post-note/<id>/update`
  - `POST /api/post-note/<id>/delete`
  - `GET /api/profile/<slug>/notes`
- **`dashboard/db.py`**: `profile_post_notes(slug)` — same shape/pattern as `profile_posts()`, attaches each note's `channels` list via a per-row `post_note_channels` lookup.

## UI

**Profile page** (`renderProfile` in `dashboard/app.js`):
- New **"📝 Log a post"** button alongside the existing profile action buttons (⚙ Setup, + Add channel). Opens a small page, same structural pattern as `renderNewMilestone`: Title (required), Date (`type="date"`, defaults to today, required), Text (optional textarea), and a row of checkboxes built from `profNode.channels` — all pre-checked, user can uncheck any/all. Saves via `POST /api/post-note/new`.
- A **"Post notes"** list block on the profile page, placed just above the post list (chronological, same register as posts). Each row shows title, date, small channel icons (reusing `PLATFORM_ICON`), and a text preview if present, with inline **Edit** (same field set as create) and **Delete** (confirm via the existing `confirmPage` helper) actions.

**Calendar** (`renderTimeline`):
- `"post_note"` added to the `kinds` array — gets its own filter chip ("Post notes") and count, same as post/activity/milestone/experiment/feature today.
- Event cell renders with a `post_note` CSS class for a distinct color/marker so it reads differently from real posts at a glance.
- Clicking the event expands detail via the existing `toggleEvDetail` pattern, showing channels + text, with inline Edit/Delete wired to the post-note endpoints — same UX milestones already have on the calendar.

## Out of scope

- No publish-gate or status workflow — a post note has no lifecycle, it just exists.
- No brief/draft generation for post notes.
- No cross-note "quick duplicate" or bulk logging — one note at a time, matching how milestones work today.
