# Post Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user log a manual, dated "I posted something" note against a profile — title, optional text, optional channel tags — separate from the OS's real `Post` pipeline, creatable/editable/deletable from the Profile page and visible on the global Calendar.

**Architecture:** New `post_notes` + `post_note_channels` tables (mirroring the existing `posts`/`post_channels` pair), sourced from one `post-notes.json` file per profile directory (mirroring how `plan-*.json` sources `posts`). Wired through the same four-layer stack every other entity in this codebase uses: `index.py` (file → SQLite), `dashboard/fileops.py` (write authored file + reindex), `dashboard/osctl.py` (CLI), `dashboard/server.py` (HTTP), `dashboard/db.py` (read), `dashboard/app.js` (UI). The `timeline` SQL view gets a new `UNION ALL` branch so post notes appear on the Calendar automatically.

**Tech Stack:** Python 3 stdlib (sqlite3, argparse, http.server — no new dependencies), vanilla JS in `dashboard/app.js` (no build step, no framework), SQLite schema in `database/migrations/0001_init.sql`.

## Global Constraints

- Public repo: never write real venture/profile/product names into tracked files (tests, fixtures) — use generic slugs (`acme`, `demo`, `demo-tiktok`). Real data only lives in gitignored `projects/`.
- `index.py` wipes and rebuilds `os.db` from authored files on every call — `database/migrations/0001_init.sql` is edited in place (no migration chain) since the DB is disposable.
- Delete endpoints for entities like milestones/posts/channels/projects are HTTP-only, never exposed as an osctl CLI command (the chat agent CLI intentionally cannot delete) — post notes follow the same rule: no `delete-post-note` osctl command.
- No JS test harness exists in this repo — frontend tasks are verified with `node --check` for syntax plus a manual browser click-through (final task), not automated tests.
- Run Python tests with: `python3 -m unittest tests.<module> -v` (no pytest installed).

---

### Task 1: Data model — `post_notes`/`post_note_channels` tables + timeline view + index.py collector

**Files:**
- Modify: `database/migrations/0001_init.sql`
- Modify: `index.py`
- Create: `tests/test_post_notes.py`

**Interfaces:**
- Produces: `index.collect_post_notes(root: Path) -> tuple[list[dict], list[dict]]`. First list = post_notes rows shaped `{"id": str, "profile_slug": str, "date": str, "title": str, "text": str|None}`. Second list = post_note_channels rows shaped `{"post_note_id": str, "channel_slug": str}`.
- Produces: SQLite tables `post_notes(id, profile_slug, date, title, text)` and `post_note_channels(post_note_id, channel_slug)`.
- Produces: `timeline` view rows with `kind='post_note'` for each note (used by every later task).

- [ ] **Step 1: Write the failing test**

Create `tests/test_post_notes.py`:

```python
import json, sqlite3, tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class PostNoteSchemaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        root = self.root
        proj = root / "projects" / "acme"
        write(proj / "project.md",
              "---\nname: Acme\nkind: venture\npriority: primary\n"
              "status: idea\nhours_per_week: 5\n---\nour voice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: cinema\nproject: acme\n---\nvoice")
        ch = prof / "channels" / "demo-tiktok"
        write(ch / "channel.md", "---\nplatform: tiktok\nhandle: @demo\n---\n")
        write(prof / "post-notes.json", json.dumps({"notes": [
            {"id": "pn-1", "date": "2026-07-14", "title": "Posted a Reel",
             "text": "quick BTS clip", "channels": ["demo-tiktok", "ghost-channel"]},
            {"id": "pn-2", "date": "2026-07-10", "title": "No-channel note"},
        ]}))
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def _con(self):
        return sqlite3.connect(self.root / "database" / "data" / "os.db")

    def test_post_notes_indexed_with_profile_slug(self):
        rows = dict(self._con().execute("SELECT id, profile_slug FROM post_notes"))
        self.assertEqual(rows, {"pn-1": "demo", "pn-2": "demo"})

    def test_valid_channel_ref_kept_unknown_channel_dropped(self):
        chans = {r[0] for r in self._con().execute(
            "SELECT channel_slug FROM post_note_channels WHERE post_note_id='pn-1'")}
        self.assertEqual(chans, {"demo-tiktok"})  # 'ghost-channel' silently dropped

    def test_timeline_includes_post_note_kind(self):
        rows = [r for r in db.timeline() if r["kind"] == "post_note"]
        ids = {r["ref_id"] for r in rows}
        self.assertEqual(ids, {"pn-1", "pn-2"})
        pn1 = next(r for r in rows if r["ref_id"] == "pn-1")
        self.assertEqual(pn1["title"], "Posted a Reel")
        self.assertEqual(pn1["entity_slug"], "demo")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: FAIL/ERROR — `sqlite3.OperationalError: no such table: post_notes`

- [ ] **Step 3: Add the two tables to the schema**

In `database/migrations/0001_init.sql`, insert right after the `post_channels` table definition (after the line `CREATE INDEX idx_posts_profile_date ON posts(profile_slug, date);` and the `post_channels` block that follows it — i.e. right before the `CREATE TABLE activities` block):

```sql
CREATE TABLE post_notes (
  id           TEXT PRIMARY KEY,
  profile_slug TEXT NOT NULL REFERENCES entities(slug),
  date         TEXT NOT NULL,
  title        TEXT NOT NULL,
  text         TEXT
);
CREATE INDEX idx_post_notes_profile_date ON post_notes(profile_slug, date);

CREATE TABLE post_note_channels (
  post_note_id TEXT NOT NULL REFERENCES post_notes(id),
  channel_slug TEXT NOT NULL REFERENCES entities(slug),
  PRIMARY KEY (post_note_id, channel_slug)
);
```

- [ ] **Step 4: Add the `post_note` branch to the `timeline` view**

In the same file, the `CREATE VIEW timeline AS` statement ends with the `milestone` branch followed by a `;`. Change that trailing `;` to `UNION ALL` and append a new final branch:

```sql
  UNION ALL
  SELECT m.date, m.date_end, m.entity_slug, 'milestone', m.title, NULL,
         COALESCE(m.priority, e.priority), e.hours_per_week, m.id
  FROM milestones m LEFT JOIN entities e ON e.slug = m.entity_slug
  UNION ALL
  SELECT n.date, NULL, n.profile_slug, 'post_note',
         n.title, NULL, e.priority, e.hours_per_week, n.id
  FROM post_notes n LEFT JOIN entities e ON e.slug = n.profile_slug;
```

- [ ] **Step 5: Add `collect_post_notes` to `index.py`**

In `index.py`, add this function right after `collect_milestones` (after its closing `return rows` around line 414):

```python
def collect_post_notes(root: Path):
    rows = {}
    chan_by_id = {}
    pdir = root / "projects"
    for proj in sorted(pdir.glob("*")) if pdir.exists() else []:
        if not proj.is_dir():
            continue
        for prof in sorted((proj / "profiles").glob("*")) if (proj / "profiles").exists() else []:
            if not prof.is_dir():
                continue
            profile_slug = prof.name
            path = prof / "post-notes.json"
            if not path.exists():
                continue
            data = load_json(path)
            for n in (data.get("notes", []) if isinstance(data, dict) else []):
                nid = n.get("id")
                date = n.get("date")
                if not nid or not date:
                    continue
                if nid in rows:
                    print(f"  warn: duplicate post note id '{nid}' — keeping latest from {rel(path, root)}")
                rows[nid] = {
                    "id": nid, "profile_slug": profile_slug, "date": date,
                    "title": n.get("title") or "(untitled)",
                    "text": n.get("text"),
                }
                chan_by_id[nid] = [c for c in (n.get("channels") or []) if c]
    post_note_channels = [
        {"post_note_id": nid, "channel_slug": c}
        for nid in rows
        for c in chan_by_id.get(nid, [])
    ]
    return list(rows.values()), post_note_channels
```

- [ ] **Step 6: Wire it into `build()`**

In `index.py`, in `build()`:

1. After the line `milestones = collect_milestones(root, slugs)` (around line 474), add:

```python
    post_notes, post_note_channels = collect_post_notes(root)
```

2. After the `post_channels = kept_pc` line (around line 501, the existing block that drops posts/post_channels referencing unknown profiles/channels), add the equivalent soft-drop for note channel refs — profile_slug for notes is always valid by construction (derived from the directory walk), only channel refs need cleaning:

```python
    kept_pnc = []
    for pnc in post_note_channels:
        if pnc["channel_slug"] in channel_slugs:
            kept_pnc.append(pnc)
        else:
            print(f"  warn: post note '{pnc['post_note_id']}' references unknown channel "
                  f"'{pnc['channel_slug']}' — dropping that channel ref")
    post_note_channels = kept_pnc
```

3. After the `INSERT INTO milestones` `cur.executemany(...)` block (around line 557), add:

```python
    cur.executemany(
        "INSERT INTO post_notes (id,profile_slug,date,title,text)"
        " VALUES (:id,:profile_slug,:date,:title,:text)",
        post_notes,
    )
    cur.executemany(
        "INSERT INTO post_note_channels (post_note_id,channel_slug) VALUES (:post_note_id,:channel_slug)",
        post_note_channels,
    )
```

4. In the `counts` dict (around line 560-564), add the two new lists:

```python
    counts = {
        "entities": entities, "relationships": relationships, "memos": memos,
        "experiments": experiments, "posts": posts, "post_channels": post_channels,
        "features": features, "activities": activities, "milestones": milestones,
        "post_notes": post_notes, "post_note_channels": post_note_channels,
    }
```

5. In the module docstring's "Reads, under WORKSPACE_ROOT" list (top of the file, around line 18-21), add a line after the posts entry:

```
    projects/<slug>/profiles/<slug>/post-notes.json -> post_notes (+ post_note_channels)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: `OK` (3 tests pass)

Run the full suite to confirm nothing else broke: `python3 -m unittest tests.test_schema tests.test_index_projects tests.test_fileops_crud -v`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add database/migrations/0001_init.sql index.py tests/test_post_notes.py
git commit -m "feat: post_notes data model (tables, timeline view, indexer)"
```

---

### Task 2: fileops CRUD — `create_post_note` / `update_post_note` / `delete_post_note`

**Files:**
- Modify: `core/ids.py`
- Modify: `dashboard/fileops.py`
- Modify: `tests/test_post_notes.py`

**Interfaces:**
- Consumes: `index.collect_post_notes` (Task 1, via `reindex()` → subprocess call to `index.py`), `fileops._profile_dir(slug) -> Path`, `fileops._parse_channels(raw: str) -> list[str]`, `fileops.reindex()`, `fileops.ActionError`.
- Produces: `core.ids.next_post_note_id(existing: set[str]) -> str` (returns `"pn-" + timestamp`).
- Produces: `fileops.create_post_note(profile_slug: str, fields: dict) -> dict` → `{"id": str, "profile_slug": str}`. Raises `ActionError` if `fields["title"]` or `fields["date"]` missing/blank.
- Produces: `fileops.update_post_note(note_id: str, fields: dict) -> dict` → `{"id": str}`. Raises `ActionError` if note not found. Accepted `fields` keys: `title`, `date`, `text`, `channels` (comma/space-separated string; empty string clears channels).
- Produces: `fileops.delete_post_note(note_id: str) -> dict` → `{"id": str, "deleted": True}`. Raises `ActionError` if note not found.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_post_notes.py`:

```python
class PostNoteCrudTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        root = self.root
        proj = root / "projects" / "acme"
        write(proj / "project.md", "---\nname: Acme\nkind: venture\npriority: primary\n---\nvoice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: cinema\n---\nvoice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---\n")
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def _con(self):
        return sqlite3.connect(self.root / "database" / "data" / "os.db")

    def test_create_post_note_requires_title_and_date(self):
        with self.assertRaises(fileops.ActionError):
            fileops.create_post_note("demo", {"date": "2026-07-14"})
        with self.assertRaises(fileops.ActionError):
            fileops.create_post_note("demo", {"title": "Posted"})

    def test_create_post_note_writes_and_indexes(self):
        out = fileops.create_post_note("demo", {
            "title": "Posted a Reel", "date": "2026-07-14",
            "text": "quick clip", "channels": "demo-tiktok",
        })
        self.assertTrue(out["id"].startswith("pn-"))
        row = dict(zip(("title", "date", "text"), self._con().execute(
            "SELECT title, date, text FROM post_notes WHERE id=?", (out["id"],)).fetchone()))
        self.assertEqual(row["title"], "Posted a Reel")
        self.assertEqual(row["text"], "quick clip")
        chans = {r[0] for r in self._con().execute(
            "SELECT channel_slug FROM post_note_channels WHERE post_note_id=?", (out["id"],))}
        self.assertEqual(chans, {"demo-tiktok"})

    def test_update_post_note_changes_title_and_clears_channels(self):
        out = fileops.create_post_note("demo", {
            "title": "Posted", "date": "2026-07-14", "channels": "demo-tiktok"})
        fileops.update_post_note(out["id"], {"title": "Big post", "channels": ""})
        row = self._con().execute("SELECT title FROM post_notes WHERE id=?", (out["id"],)).fetchone()
        self.assertEqual(row[0], "Big post")
        chans = self._con().execute(
            "SELECT channel_slug FROM post_note_channels WHERE post_note_id=?", (out["id"],)).fetchall()
        self.assertEqual(chans, [])

    def test_update_post_note_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_post_note("pn-zzz", {"title": "X"})

    def test_delete_post_note_removes_it(self):
        out = fileops.create_post_note("demo", {"title": "Posted", "date": "2026-07-14"})
        fileops.delete_post_note(out["id"])
        row = self._con().execute("SELECT id FROM post_notes WHERE id=?", (out["id"],)).fetchone()
        self.assertIsNone(row)

    def test_delete_post_note_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_post_note("pn-zzz")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: FAIL — `AttributeError: module 'dashboard.fileops' has no attribute 'create_post_note'`

- [ ] **Step 3: Add `next_post_note_id` to `core/ids.py`**

In `core/ids.py`, right after `next_milestone_id` (around line 741-742):

```python
def next_post_note_id(existing: set[str]) -> str:
    return _stamp("pn-", existing)
```

- [ ] **Step 4: Import it in `dashboard/fileops.py`**

In `dashboard/fileops.py`, in the `from core.ids import (...)` block (lines 37-50), insert `next_post_note_id,` right after `next_post_id,` (keeping the existing alphabetical order):

```python
from core.ids import (
    build_id_registry,
    lk_experiment,
    lk_feature,
    lk_fld_brief,
    lk_memo,
    lk_prod,
    next_activity_id,
    next_experiment_stem,
    next_memo_version,
    next_milestone_id,
    next_post_id,
    next_post_note_id,
    slug_key,
)
```

- [ ] **Step 5: Implement the three functions**

In `dashboard/fileops.py`, add this block right after `delete_milestone` (after its closing `return {"id": ms_id, "deleted": True}` around line 967), before `_roadmap_section_name`:

```python
_POST_NOTE_FIELDS = ("title", "date", "text")


def _find_post_note(note_id: str):
    """Locate the post-notes.json file + note object for a note id."""
    for path in sorted(ROOT.glob("projects/*/profiles/*/post-notes.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for note in data.get("notes", []) if isinstance(data, dict) else []:
            if note.get("id") == note_id:
                return {"path": path, "data": data, "note": note}
    raise ActionError(f"post note '{note_id}' not found")


def create_post_note(profile_slug: str, fields: dict) -> dict:
    title = (fields.get("title") or "").strip()
    date = (fields.get("date") or "").strip()
    if not title:
        raise ActionError("title is required")
    if not date:
        raise ActionError("date is required")
    profile_dir = _profile_dir(profile_slug)
    path = profile_dir / "post-notes.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"notes": []}
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
            data = {"notes": []}
    else:
        data = {"notes": []}
    existing_ids = {n.get("id") for n in data.get("notes", [])}
    note_id = next_post_note_id(existing_ids)
    note: dict = {"id": note_id, "title": title, "date": date}
    if fields.get("text"):
        note["text"] = fields["text"].strip()
    channels = _parse_channels(fields.get("channels"))
    if channels:
        note["channels"] = channels
    data.setdefault("notes", []).append(note)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": note_id, "profile_slug": profile_slug}


def update_post_note(note_id: str, fields: dict) -> dict:
    """Edit one post note in its profile's post-notes.json. Empty values clear the field."""
    ctx = _find_post_note(note_id)
    note = ctx["note"]
    for k in _POST_NOTE_FIELDS:
        if k not in fields or fields[k] is None:
            continue
        v = str(fields[k]).strip()
        if v:
            note[k] = v
        else:
            note.pop(k, None)
    if "channels" in fields:
        channels = _parse_channels(fields.get("channels"))
        if channels:
            note["channels"] = channels
        else:
            note.pop("channels", None)
    ctx["path"].write_text(json.dumps(ctx["data"], indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": note_id}


def delete_post_note(note_id: str) -> dict:
    ctx = _find_post_note(note_id)
    ctx["data"]["notes"] = [n for n in ctx["data"]["notes"] if n.get("id") != note_id]
    ctx["path"].write_text(json.dumps(ctx["data"], indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": note_id, "deleted": True}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: `OK` (9 tests pass — 3 from Task 1 + 6 new)

- [ ] **Step 7: Commit**

```bash
git add core/ids.py dashboard/fileops.py tests/test_post_notes.py
git commit -m "feat: post note CRUD in fileops (create/update/delete)"
```

---

### Task 3: `db.py` read query — `profile_post_notes`

**Files:**
- Modify: `dashboard/db.py`
- Modify: `tests/test_post_notes.py`

**Interfaces:**
- Consumes: `dashboard.fileops.create_post_note` (Task 2), `dashboard.db._rows`.
- Produces: `dashboard.db.profile_post_notes(slug: str) -> list[dict]`. Each dict: `{id, profile_slug, date, title, text, channels: [str, ...]}`, ordered newest date first (most-recently-posted first, unlike `profile_posts` which sorts oldest-first/upcoming).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_post_notes.py`:

```python
class ProfilePostNotesQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        root = self.root
        proj = root / "projects" / "acme"
        write(proj / "project.md", "---\nname: Acme\nkind: venture\npriority: primary\n---\nvoice")
        prof = proj / "profiles" / "demo"
        write(prof / "profile.md", "---\nname: Demo\ntopic: cinema\n---\nvoice")
        write(prof / "channels" / "demo-tiktok" / "channel.md", "---\nplatform: tiktok\n---\n")
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)
        fileops.create_post_note("demo", {"title": "Older", "date": "2026-07-01"})
        fileops.create_post_note("demo", {"title": "Newer", "date": "2026-07-14", "channels": "demo-tiktok"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_post_notes_ordered_newest_first_with_channels(self):
        notes = db.profile_post_notes("demo")
        self.assertEqual([n["title"] for n in notes], ["Newer", "Older"])
        self.assertEqual(notes[0]["channels"], ["demo-tiktok"])
        self.assertEqual(notes[1]["channels"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: FAIL — `AttributeError: module 'dashboard.db' has no attribute 'profile_post_notes'`

- [ ] **Step 3: Implement the query**

In `dashboard/db.py`, add this right after `profile_posts` (after its `return rows` around line 169):

```python
def profile_post_notes(slug):
    """All post notes for one profile, newest first, with channels attached."""
    rows = _rows(
        "SELECT id, profile_slug, date, title, text"
        " FROM post_notes WHERE profile_slug = ?"
        " ORDER BY date DESC",
        (slug,),
    )
    for note in rows:
        ch_rows = _rows(
            "SELECT channel_slug FROM post_note_channels WHERE post_note_id = ? ORDER BY channel_slug",
            (note["id"],),
        )
        note["channels"] = [r["channel_slug"] for r in ch_rows]
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_post_notes -v`
Expected: `OK` (10 tests pass)

- [ ] **Step 5: Commit**

```bash
git add dashboard/db.py tests/test_post_notes.py
git commit -m "feat: db.profile_post_notes query"
```

---

### Task 4: osctl CLI — `create-post-note` / `update-post-note`

**Files:**
- Modify: `dashboard/osctl.py`
- Modify: `tests/test_osctl.py`

**Interfaces:**
- Consumes: `fileops.create_post_note(profile_slug, fields)`, `fileops.update_post_note(note_id, fields)` (Task 2).
- Produces: CLI subcommands `create-post-note --profile --title --date [--text] [--channels]` and `update-post-note --id [--title] [--date] [--text] [--channels]`, each printing one JSON line via the existing `_emit` convention.
- No `delete-post-note` command — matches the existing convention that destructive ops (milestone/post/channel/project delete) are HTTP-only, not exposed to the CLI/chat agent.

- [ ] **Step 1: Write the failing test**

Append to the `T` class in `tests/test_osctl.py` (after `test_update_milestone`, around line 104):

```python
    def test_create_and_update_post_note(self):
        run(["create-project", "--slug", "acme"])
        run(["create-profile", "--project", "acme", "--slug", "demo"])
        run(["create-channel", "--profile", "demo", "--slug", "demo-tiktok", "--platform", "tiktok"])
        c, out = run(["create-post-note", "--profile", "demo", "--title", "Posted a Reel",
                      "--date", "2026-07-14", "--channels", "demo-tiktok"])
        self.assertEqual(c, 0); self.assertTrue(out["id"].startswith("pn-"))
        self.assertEqual(len(db.profile_post_notes("demo")), 1)

        c, out = run(["update-post-note", "--id", out["id"], "--title", "Bigger post"])
        self.assertEqual(c, 0); self.assertTrue(out["ok"])
        self.assertEqual(db.profile_post_notes("demo")[0]["title"], "Bigger post")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_osctl -v`
Expected: FAIL — `SystemExit: 2` (argparse: unrecognized subcommand `create-post-note`)

- [ ] **Step 3: Add the subcommands**

In `dashboard/osctl.py`, insert right after the `update-milestone` block (after its `p.set_defaults(...)` call, around line 329), before the `# Content generation` comment:

```python
    p = sub.add_parser("create-post-note")
    p.add_argument("--profile", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--text")
    p.add_argument("--channels")
    p.set_defaults(_run=lambda a: fileops.create_post_note(
        a.profile, _fields(a, ["title", "date", "text", "channels"])))

    p = sub.add_parser("update-post-note")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--title")
    p.add_argument("--date")
    p.add_argument("--text")
    p.add_argument("--channels")
    p.set_defaults(_run=lambda a: fileops.update_post_note(a.id, _fields(
        a, ["title", "date", "text", "channels"])))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_osctl -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add dashboard/osctl.py tests/test_osctl.py
git commit -m "feat: create-post-note/update-post-note osctl commands"
```

---

### Task 5: server.py HTTP routes

**Files:**
- Modify: `dashboard/server.py`

**Interfaces:**
- Consumes: `db.profile_post_notes(slug)` (Task 3), `fileops.create_post_note`, `fileops.update_post_note`, `fileops.delete_post_note` (Task 2).
- Produces: `GET /api/profile/<slug>/notes` → JSON array (same shape as `db.profile_post_notes`). `POST /api/post-note/new` (body must include `profile`) → `{"ok": true, "id": ..., "profile_slug": ...}`. `POST /api/post-note/<id>/update` → `{"ok": true, "id": ...}`. `POST /api/post-note/<id>/delete` → `{"ok": true, "id": ..., "deleted": true}`.

- [ ] **Step 1: Add the GET route**

In `dashboard/server.py`, in `do_GET`, insert right after the `/posts` block (after `return self._send(200, db.profile_posts(slug))`, around line 623), before the generic `/api/profile/` fallback:

```python
            if path.startswith("/api/profile/") and path.endswith("/notes"):
                slug = path[len("/api/profile/"):-len("/notes")]
                return self._send(200, db.profile_post_notes(slug))
```

- [ ] **Step 2: Add the POST routes**

In `dashboard/server.py`, in `do_POST`, insert right after the milestone delete block (after `return self._send(200, {"ok": True, **fileops.delete_milestone(ms_id)})`, around line 782), before `if path == "/api/ask":`:

```python
            if path == "/api/post-note/new":
                return self._send(200, {"ok": True, **fileops.create_post_note(body.get("profile", ""), body)})
            if path.startswith("/api/post-note/") and path.endswith("/update"):
                note_id = path[len("/api/post-note/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_post_note(note_id, body)})
            if path.startswith("/api/post-note/") and path.endswith("/delete"):
                note_id = path[len("/api/post-note/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_post_note(note_id)})
```

- [ ] **Step 3: Verify by hand (no HTTP test harness exists in this repo for route wiring — every other CRUD route, e.g. milestone/channel, is verified the same way)**

Run: `python3 -m py_compile dashboard/server.py`
Expected: no output (syntax OK)

Then, from the repo root, in one terminal:
```bash
python3 dashboard/server.py --port 8765
```
In another terminal (against a real or scratch profile that already exists under `projects/`, created e.g. via `python3 -m dashboard.osctl create-project --slug acme` + `create-profile --project acme --slug demo` if needed):
```bash
curl -s -X POST localhost:8765/api/post-note/new \
  -H 'Content-Type: application/json' \
  -d '{"profile":"demo","title":"Posted a Reel","date":"2026-07-14"}'
curl -s localhost:8765/api/profile/demo/notes
```
Expected: first call returns `{"ok": true, "id": "pn-...", "profile_slug": "demo"}`; second call returns a JSON array containing that note. Stop the server (Ctrl-C) when done.

- [ ] **Step 4: Commit**

```bash
git add dashboard/server.py
git commit -m "feat: post-note HTTP routes (GET notes, POST new/update/delete)"
```

---

### Task 6: Frontend — New/Edit Post Note pages + routes

**Files:**
- Modify: `dashboard/app.js`
- Modify: `dashboard/app.css`

**Interfaces:**
- Consumes: `api`, `jpost`, `esc`, `$`, `flabel`, `finput`, `fta`, `formVals`, `pageHeader`, `toast`, `navigate`, `_TREE`, `PLATFORM_ICON` (all pre-existing app.js globals/helpers).
- Produces: `renderNewPostNote(profileSlug: string, extras={}) -> Promise<void>`, `renderEditPostNote(id: string, extras={}) -> Promise<void>`. Routes `#/postnote/new` (reads `_NAV_EXTRAS.profileSlug`) and `#/postnote/:id/edit` (reads `_NAV_EXTRAS.profileSlug`, `.title`, `.date`, `.text`, `.channels`) — these are the exact extras shapes Task 7 and Task 8 must pass when navigating here.

- [ ] **Step 1: Add the two routes**

In `dashboard/app.js`, in the `ROUTES` array, insert right after the milestone edit route (after line 193):

```js
  [/^\/postnote\/new$/,                         ()       => renderNewPostNote(_NAV_EXTRAS.profileSlug, _NAV_EXTRAS)],
  [/^\/postnote\/([^/]+)\/edit$/,               ([id])   => renderEditPostNote(id, _NAV_EXTRAS)],
```

- [ ] **Step 2: Add the two render functions**

In `dashboard/app.js`, insert right after `renderEditMilestone` (after its closing `}` around line 1925), before the `// ── Confirm / delete pages ─` comment:

```js
async function renderNewPostNote(profileSlug, extras={}){
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{name:profileSlug,channels:[]};
  const channels=profNode.channels||[];
  const today=new Date().toISOString().slice(0,10);
  const chanBoxes=channels.map(ch=>`<label style="display:inline-flex;align-items:center;gap:6px;margin:4px 14px 4px 0;cursor:pointer">
    <input type="checkbox" class="note-chan" value="${esc(ch.slug)}" checked> ${PLATFORM_ICON[ch.platform]||"⌗"} ${esc(ch.name||ch.platform)}</label>`).join("");
  $("#main").innerHTML=`${pageHeader("Log a post", profNode.name||profileSlug, `<button class="btn primary" id="pn-save">Save note</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("title","",'placeholder="e.g. Posted a quick BTS clip" required')}
      ${flabel("Date")}${finput("date",today,'type="date" required')}
      ${flabel("Text (optional)")}${fta("text","",4,'placeholder="optional detail"')}
      ${channels.length?`${flabel("Channels")}<div>${chanBoxes}</div>`:""}
    </div></div>`;
  document.getElementById("pn-save").onclick=async()=>{
    const data=formVals($("#main"));
    const chans=[...$("#main").querySelectorAll(".note-chan:checked")].map(c=>c.value);
    try{
      await jpost("/api/post-note/new",{profile:profileSlug,title:data.title,date:data.date,text:data.text,channels:chans.join(",")});
      toast("Note logged ✓"); history.back();
    }catch(e){ toast("✗ "+e.message); }
  };
}

async function renderEditPostNote(id, extras={}){
  const profileSlug = extras.profileSlug||"";
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{name:profileSlug,channels:[]};
  const channels=profNode.channels||[];
  const selected=new Set(extras.channels||[]);
  const chanBoxes=channels.map(ch=>`<label style="display:inline-flex;align-items:center;gap:6px;margin:4px 14px 4px 0;cursor:pointer">
    <input type="checkbox" class="note-chan" value="${esc(ch.slug)}" ${selected.has(ch.slug)?"checked":""}> ${PLATFORM_ICON[ch.platform]||"⌗"} ${esc(ch.name||ch.platform)}</label>`).join("");
  $("#main").innerHTML=`${pageHeader("Edit note", profNode.name||profileSlug, `<button class="btn primary" id="pn-save">Save</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("title",extras.title||"",'required')}
      ${flabel("Date")}${finput("date",extras.date||"",'type="date" required')}
      ${flabel("Text (optional)")}${fta("text",extras.text||"",4,'placeholder="optional detail"')}
      ${channels.length?`${flabel("Channels")}<div>${chanBoxes}</div>`:""}
    </div></div>`;
  document.getElementById("pn-save").onclick=async()=>{
    const data=formVals($("#main"));
    const chans=[...$("#main").querySelectorAll(".note-chan:checked")].map(c=>c.value);
    try{
      await jpost(`/api/post-note/${id}/update`,{title:data.title,date:data.date,text:data.text,channels:chans.join(",")});
      toast("Note updated ✓"); history.back();
    }catch(e){ toast("✗ "+e.message); }
  };
}
```

- [ ] **Step 3: Add supporting CSS**

In `dashboard/app.css`, add two new color variables in the `:root{...}` block (right after the `--amber`/`--amber-soft` line, around line 8):

```css
    --rose:#c2447b; --rose-soft:rgba(194,68,123,.14);
```

Add a `.stp.note` variant right after the existing `.stp.ready`/`.stp.sched` line (around line 174):

```css
  .stp.note{background:var(--rose-soft);color:var(--rose)}
```

- [ ] **Step 4: Verify syntax**

Run: `node --check dashboard/app.js`
Expected: no output (exit code 0)

(These new functions aren't reachable from any button yet — Task 8 wires the entry point. Full click-through happens at the end of Task 8.)

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js dashboard/app.css
git commit -m "feat: New/Edit Post Note pages and routes"
```

---

### Task 7: Frontend — Calendar surfacing

**Files:**
- Modify: `dashboard/app.js`
- Modify: `dashboard/app.css`

**Interfaces:**
- Consumes: `renderNewPostNote`/routes from Task 6 (edit navigation target `#/postnote/:id/edit`), `jpost`, `undoToast`, `refreshViews`, `navigate`.
- Produces: `"post_note"` kind now flows through `renderTimeline`'s existing kind-filter/count/render machinery; `evDetail(r)` gains post_note-aware Edit/Delete actions.

- [ ] **Step 1: Add `"post_note"` to the kinds list**

In `dashboard/app.js`, in `renderTimeline` (around line 1022), change:

```js
  const kinds=["post","activity","milestone","experiment","feature"];
```

to:

```js
  const kinds=["post","activity","milestone","experiment","feature","post_note"];
```

- [ ] **Step 2: Add post_note actions to `evDetail`**

In `dashboard/app.js`, in `evDetail(r)` (around line 963), add a branch right after the existing milestone-actions branch (after `if(r.kind==="milestone"&&r.ref_id){...}`, around line 977):

```js
  if(r.kind==="post_note"&&r.ref_id){
    acts+=`<button class="btn primary" data-ev-edit>Edit</button>`;
    acts+=`<button class="btn danger-btn" data-ev-del>Delete</button>`;
  }
```

- [ ] **Step 3: Extend the delete handler**

Still in `evDetail(r)`, the delete button handler (`delBtn.onclick=async()=>{...}`) currently ends with the milestone `else if` branch (around lines 998-1007). Add a new `else if` branch right after it, before the handler's closing `};`:

```js
    } else if(r.kind==="post_note"&&r.ref_id){
      try{
        await jpost(`/api/post-note/${r.ref_id}/delete`,{});
        undoToast(`Note "${r.title}" deleted`, async()=>{
          await jpost("/api/post-note/new",{profile:r.entity_slug,title:r.title,date:r.date});
          refreshViews();
        });
        refreshViews();
      }catch(e){ toast("✗ "+e.message); }
    }
```

- [ ] **Step 4: Make the edit handler kind-aware**

Still in `evDetail(r)`, the edit handler currently hardcodes the milestone route (around line 1010):

```js
  const editBtn=d.querySelector("[data-ev-edit]");
  if(editBtn) editBtn.onclick=()=>navigate(`#/milestone/${r.ref_id}/edit`,{title:r.title,date:r.date,date_end:r.date_end||""});
```

Replace it with:

```js
  const editBtn=d.querySelector("[data-ev-edit]");
  if(editBtn) editBtn.onclick=()=>{
    if(r.kind==="post_note") navigate(`#/postnote/${r.ref_id}/edit`,{profileSlug:r.entity_slug,title:r.title,date:r.date});
    else navigate(`#/milestone/${r.ref_id}/edit`,{title:r.title,date:r.date,date_end:r.date_end||""});
  };
```

- [ ] **Step 5: Add calendar CSS**

In `dashboard/app.css`, add a new `.ev.post_note` rule right after the existing `.ev.milestone` rule (around line 294):

```css
  .ev.post_note{background:var(--rose-soft);color:var(--rose);cursor:pointer}
```

Add a matching filter-chip rule right after `.kchip.k-milestone.on` (around line 318):

```css
  .kchip.k-post_note.on{background:var(--rose-soft);color:var(--rose)}
```

- [ ] **Step 6: Verify syntax**

Run: `node --check dashboard/app.js`
Expected: no output (exit code 0)

- [ ] **Step 7: Commit**

```bash
git add dashboard/app.js dashboard/app.css
git commit -m "feat: surface post notes on the Calendar"
```

---

### Task 8: Frontend — Profile page integration + end-to-end verification

**Files:**
- Modify: `dashboard/app.js`

**Interfaces:**
- Consumes: `GET /api/profile/<slug>/notes` (Task 5), `renderNewPostNote`/`#/postnote/new` route (Task 6), `#/postnote/:id/edit` route (Task 6), `jpost`, `undoToast`, `PLATFORM_ICON`.
- Produces: a "📝 Log a post" button and a "Post notes" list on the Profile page (`renderProfile`), wired to create/edit/delete.

- [ ] **Step 1: Fetch notes alongside posts**

In `dashboard/app.js`, in `renderProfile` (around line 1071), change:

```js
  const [posts, profData] = await Promise.all([
    api(`/api/profile/${slug}/posts`),
    api(`/api/profile/${slug}`),
    ensureIdRegistry(),
  ]);
```

to:

```js
  const [posts, profData, notes] = await Promise.all([
    api(`/api/profile/${slug}/posts`),
    api(`/api/profile/${slug}`),
    api(`/api/profile/${slug}/notes`),
    ensureIdRegistry(),
  ]);
```

- [ ] **Step 2: Add the "Log a post" button**

Still in `renderProfile`, change the `profBtns` definition (around line 1089):

```js
  const profBtns = `<button class="btn" id="setupBtn">⚙ Setup</button>`
    + `<button class="btn" id="addIdea">＋ Add idea</button>`
    + `<button class="btn" id="writeAll">✍ Write all ideas</button>`
    + `<button class="btn primary" id="genIdeas">✦ Generate ideas</button>`;
```

to:

```js
  const profBtns = `<button class="btn" id="setupBtn">⚙ Setup</button>`
    + `<button class="btn" id="logNoteBtn">📝 Log a post</button>`
    + `<button class="btn" id="addIdea">＋ Add idea</button>`
    + `<button class="btn" id="writeAll">✍ Write all ideas</button>`
    + `<button class="btn primary" id="genIdeas">✦ Generate ideas</button>`;
```

- [ ] **Step 3: Add a notes container to the page markup**

Still in `renderProfile`, change the `$("#main").innerHTML = ...` block (around line 1093-1104) to insert a `<div id="notesList">` between `chanSection` and the filters block:

```js
  $("#main").innerHTML = `${pageHeader(profData.name||slug, "Profiles", profBtns, OSID.prof(slug))}
    <div style="padding:0 24px 8px;font-size:12px;color:var(--dim)">${posts.length} posts</div>
    <div class="scroll">
      ${chanSection}
      <div id="notesList"></div>
      <div class="filters">
        <span class="chip on" data-f="all">All <span class="n">${posts.length}</span></span>
        <span class="chip" data-f="ideas">💡 Ideas <span class="n">${count("ideas")}</span></span>
        <span class="chip" data-f="drafts">✍ Drafts <span class="n">${count("drafts")}</span></span>
        <span class="chip" data-f="published">✓ Published <span class="n">${count("published")}</span></span>
      </div>
      <div id="selbar"></div>
      <div class="rowc" id="list"></div></div>`;
```

- [ ] **Step 4: Add `drawNotes()` and wire it up**

Still in `renderProfile`, add this function right after `drawSelBar()` (after its closing `}` around line 1121), before `function drawList(){`:

```js
  function drawNotes(){
    const el = $("#notesList");
    if(!el) return;
    if(!notes.length){ el.innerHTML=""; return; }
    el.innerHTML = `<div class="label" style="margin:2px 2px 8px">Post notes</div>` + notes.map(n=>{
      const chanIcons = (n.channels||[]).map(cs=>{
        const ch=channels.find(c=>c.slug===cs);
        return `<span title="${esc(ch?.name||cs)}">${PLATFORM_ICON[ch?.platform]||"⌗"}</span>`;
      }).join(" ");
      return `<div class="post">
        <span class="stp note">Note</span>
        <div class="t">${esc(n.title)}<small>${[n.date, chanIcons].filter(Boolean).join(" · ")}</small>${n.text?`<div style="margin-top:4px;color:var(--ink2)">${esc(n.text)}</div>`:""}</div>
        <button class="more" data-note-edit="${esc(n.id)}">Edit</button>
        <button class="more" data-note-del="${esc(n.id)}">Delete</button></div>`;
    }).join("");
    el.querySelectorAll("[data-note-edit]").forEach(b=>b.onclick=()=>{
      const n=notes.find(x=>x.id===b.dataset.noteEdit);
      navigate(`#/postnote/${n.id}/edit`,{profileSlug:slug,title:n.title,date:n.date,text:n.text||"",channels:n.channels||[]});
    });
    el.querySelectorAll("[data-note-del]").forEach(b=>b.onclick=async()=>{
      const n=notes.find(x=>x.id===b.dataset.noteDel);
      try{
        await jpost(`/api/post-note/${n.id}/delete`,{});
        notes.splice(notes.indexOf(n),1);
        drawNotes();
        undoToast(`Note "${n.title}" deleted`, async()=>{
          await jpost("/api/post-note/new",{profile:slug,title:n.title,date:n.date,text:n.text||"",channels:(n.channels||[]).join(",")});
          renderProfile(slug);
        });
      }catch(e){ toast("✗ "+e.message); }
    });
  }
```

- [ ] **Step 5: Wire the button and call `drawNotes()`**

Still in `renderProfile`, change the bottom wiring block (around lines 1169-1174):

```js
  $("#writeAll").onclick=()=>writeAllIdeas(slug);
  $("#addChanBtn").onclick=e=>{ e.stopPropagation(); openNewChannel(slug); };
  $("#setupBtn").onclick=()=>navigate(`#/profile/${slug}/setup`);
  $("#addIdea").onclick=()=>navigate(`#/profile/${slug}/add`);
  $("#genIdeas").onclick=()=>navigate(`#/profile/${slug}/generate`);
  drawList();
}
```

to:

```js
  $("#writeAll").onclick=()=>writeAllIdeas(slug);
  $("#addChanBtn").onclick=e=>{ e.stopPropagation(); openNewChannel(slug); };
  $("#setupBtn").onclick=()=>navigate(`#/profile/${slug}/setup`);
  $("#logNoteBtn").onclick=()=>navigate(`#/postnote/new`,{profileSlug:slug});
  $("#addIdea").onclick=()=>navigate(`#/profile/${slug}/add`);
  $("#genIdeas").onclick=()=>navigate(`#/profile/${slug}/generate`);
  drawList();
  drawNotes();
}
```

- [ ] **Step 6: Verify syntax**

Run: `node --check dashboard/app.js`
Expected: no output (exit code 0)

- [ ] **Step 7: Run the full Python test suite**

Run: `python3 -m unittest discover -s tests -v 2>&1 | tail -30`
Expected: `OK` — no regressions across the whole suite.

- [ ] **Step 8: Manual end-to-end verification in the browser**

Per this project's standing rule for UI changes: start the dashboard and drive the actual feature before calling it done.

```bash
python3 dashboard/server.py --port 8765
```

Open `http://localhost:8765` (or use the claude-in-chrome tool) and:
1. Navigate to a profile that has at least one channel.
2. Click "📝 Log a post" — fill in Title + Date, leave Text blank, uncheck one channel, save. Confirm it lands back on the profile page under a new "Post notes" section with the right channel icon(s).
3. Click "Edit" on that note, change the title, save. Confirm the title updates in the list.
4. Click "Delete" on the note. Confirm it disappears and an undo toast appears; click Undo and confirm it reappears.
5. Navigate to the Calendar. Confirm the note shows up on its date with the rose-colored `post_note` styling, that the "Post notes" filter chip appears with the right count, and that clicking the event lets you Edit/Delete it from there too.

If any step fails, fix the underlying code (don't skip this check) and re-verify.

- [ ] **Step 9: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: Post notes on the Profile page (log/edit/delete)"
```
