# @-mention posts by id in chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each post @-referenceable in the dashboard chat by its post id (e.g. `@post-001`), inlining its full content into chat context like the currently-open post already is.

**Architecture:** Add a flat `/api/posts-index` endpoint backed by the existing `db.posts()` query (already returns every post across all profiles). The chat client fetches it alongside `_TREE` in `renderRail()`, caches it in a `_POSTS` global, and feeds posts into the existing @-mention autocomplete. On send, `buildContext` becomes async: any surviving `@post-xxx` token is resolved via the existing `GET /api/post/{id}` route and its slot+brief JSON is inlined (capped, deduped against the open post).

**Tech Stack:** Python stdlib `http.server` (`dashboard/server.py`), SQLite read layer (`dashboard/db.py`), vanilla JS frontend (`dashboard/app.js`), `unittest` tests.

## Global Constraints

- Source of truth is authored files; `os.db` is a derived, disposable index. This feature is read-only against the index — no schema changes, no migrations.
- `db.posts()` already exists and returns: `id, profile_slug, profile_name, date, pillar, working_title, concept, status, version, brief_path`. Reuse it; do **not** add a fileops helper.
- Cap inline full-content posts at **5** per message; beyond the cap, include id + label only.
- All posts in the index (not profile-scoped). `@post-001` resolves from any view.
- Not in scope: metadata tag field, tag filtering, controlled vocab.

---

### Task 1: `/api/posts-index` endpoint

**Files:**
- Modify: `dashboard/server.py:256-257` (insert new route beside `/api/tree`)
- Test: `tests/test_db_tree.py` (add a posts-index test class, reuses the same tree writer)

**Interfaces:**
- Consumes: `db.posts()` — existing, returns `list[dict]` with keys `id, profile_slug, profile_name, date, pillar, working_title, concept, status, version, brief_path`.
- Produces: `GET /api/posts-index` → `200` with that list as JSON. The client reads `id`, `working_title`, `pillar`, `status`, `profile_slug`, `profile_name`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db_tree.py` (the `_db` helper already builds a one-post index; reuse it):

```python
class TestPostsIndex(unittest.TestCase):
    def test_posts_returns_all_with_profile_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = TestTree()._db(tmp)
            rows = db.posts()
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r["id"], "p1")
            self.assertEqual(r["profile_slug"], "demo")
            self.assertEqual(r["profile_name"], "Demo")
            for key in ("pillar", "working_title", "status"):
                self.assertIn(key, r)
```

- [ ] **Step 2: Run test to verify it passes for db, then confirm the route is missing**

Run: `python -m pytest tests/test_db_tree.py::TestPostsIndex -v`
Expected: PASS (db.posts() already exists). This pins the contract the endpoint depends on.

- [ ] **Step 3: Add the route**

In `dashboard/server.py`, immediately after the `/api/tree` block (currently lines 256-257):

```python
            if path == "/api/posts-index":
                return self._send(200, db.posts())
```

- [ ] **Step 4: Verify the endpoint manually**

Run (from repo root, with an indexed `os.db` present):
`python -c "import json,dashboard.db as db; print(json.dumps(db.posts())[:200])"`
Expected: a JSON array of post dicts (or `[]` if no posts indexed). Confirms `db.posts()` is importable and shaped as the route returns it.

- [ ] **Step 5: Commit**

```bash
git add dashboard/server.py tests/test_db_tree.py
git commit -m "feat: add /api/posts-index endpoint for chat @-mentions"
```

---

### Task 2: Post candidates in @-mention autocomplete

**Files:**
- Modify: `dashboard/app.js:89` (add `_POSTS` global beside `_TREE`)
- Modify: `dashboard/app.js:124` (fetch posts-index in `renderRail` alongside `/api/tree`)
- Modify: `dashboard/app.js:1191-1202` (`mentionCandidates` appends posts)
- Modify: `dashboard/app.js:1219` (`ICON` map gains `post`)

**Interfaces:**
- Consumes: `GET /api/posts-index` from Task 1; the existing `api(path)` fetch helper; `mentionCandidates()` returns `list[{type, slug, name, meta}]`; `pickMention` pushes `{token, type, slug, name}` to `mentions[]` (generic — already works for any `type`).
- Produces: post candidates with `type:"post"`, `slug:<post id>`, `name:<label>`, `meta:"<profile_name> · <status>"`. Token form `@<post id>`.

- [ ] **Step 1: Add the `_POSTS` global**

At `dashboard/app.js:89`, after `let _TREE = [];`:

```javascript
let _TREE = [];
let _POSTS = [];   // flat post index for @-mentions, refreshed in renderRail
```

- [ ] **Step 2: Fetch the index in `renderRail`**

At `dashboard/app.js:124`, change the single tree fetch to fetch both in parallel:

```javascript
  [_TREE, _POSTS] = await Promise.all([
    api("/api/tree"),
    api("/api/posts-index").catch(() => []),
  ]);
```

(The `.catch(() => [])` keeps the rail rendering even if the posts route 500s.)

- [ ] **Step 3: Append posts in `mentionCandidates`**

Replace the body of `mentionCandidates()` (`dashboard/app.js:1191-1202`) so it adds posts after the tree walk:

```javascript
  function mentionCandidates(){
    const out = [];
    for (const p of _TREE) {
      out.push({ type:"project", slug:p.slug, name:p.name, meta:(p.kind||p.type||"project") });
      for (const prof of (p.profiles||[])) {
        out.push({ type:"profile", slug:prof.slug, name:prof.name, meta:"profile" });
        for (const ch of (prof.channels||[]))
          out.push({ type:"channel", slug:ch.slug, name:(ch.name||ch.platform), meta:(ch.platform||"channel") });
      }
    }
    for (const post of _POSTS) {
      out.push({
        type:"post",
        slug:post.id,
        name:(post.working_title || post.pillar || post.id),
        meta:`${post.profile_name||post.profile_slug} · ${post.status||""}`.trim(),
      });
    }
    return out;
  }
```

- [ ] **Step 4: Add the post icon**

At `dashboard/app.js:1219`, extend the `ICON` map:

```javascript
    const ICON = { project:"▣", profile:"◐", channel:"▶", post:"✎" };
```

- [ ] **Step 5: Manual verify in the browser**

Start the dashboard, open chat, type `@`. Expected: post entries appear in the autocomplete with the `✎` icon and a `<profile> · <status>` meta line; filtering by part of a post id or working title narrows the list; selecting one inserts `@<post-id>`.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: surface posts as @-mention candidates in chat"
```

---

### Task 3: Inline referenced-post content in `buildContext`

**Files:**
- Modify: `dashboard/app.js:1315-1342` (make `buildContext` async; split entity vs post refs; inline post content with cap + dedupe)
- Modify: `dashboard/app.js:1357` (`await` the now-async `buildContext`)

**Interfaces:**
- Consumes: `mentions[]` entries `{token, type, slug, name}`; `GET /api/post/{id}` → `{slot, brief, profile_slug}` (existing route, `dashboard/server.py:277-279`); `CURRENT_POST` global `{id, slot, brief}` or `null`; `api(path)` fetch helper.
- Produces: `buildContext(text)` now returns `Promise<string>`. Non-post mentions still render in the `## Referenced entities` block (unchanged shape). Each referenced post renders a `## Referenced post (id: …)` block with full slot+brief JSON, capped at 5, skipping any id equal to `CURRENT_POST.id` and de-duplicating repeated tokens.

- [ ] **Step 1: Rewrite `buildContext` as async with post inlining**

Replace `dashboard/app.js:1315-1342` (the whole `buildContext` function) with:

```javascript
  async function buildContext(text){
    const title = document.querySelector(".title");
    const crumbs = document.querySelector(".crumbs");
    let ctx = "";
    if (crumbs) ctx += "Current view: " + crumbs.textContent + "\n";
    if (title)  ctx += "Section: " + title.textContent + "\n";
    // resolve @-mentions still present in the message
    const refs = mentions.filter(m => text.includes(m.token));
    // non-post mentions: identity only, as before
    const entRefs = refs.filter(m => m.type !== "post");
    if (entRefs.length) {
      ctx += "\n## Referenced entities\n" + entRefs.map(m =>
        `- ${m.type} "${m.name}" (slug: ${m.slug})`
      ).join("\n") + "\n";
    }
    // post mentions: inline full slot+brief. Dedupe (incl. the open post) and cap.
    const seen = new Set(CURRENT_POST ? [CURRENT_POST.id] : []);
    const postRefs = [];
    for (const m of refs) {
      if (m.type !== "post" || seen.has(m.slug)) continue;
      seen.add(m.slug); postRefs.push(m);
    }
    const CAP = 5;
    for (const m of postRefs.slice(0, CAP)) {
      let body;
      try {
        const d = await api("/api/post/" + m.slug);
        body = "Full content:\n```json\n"
             + JSON.stringify({ slot: d.slot, brief: d.brief }, null, 2)
             + "\n```\n";
      } catch {
        body = "(could not load content)\n";
      }
      ctx += `\n## Referenced post (id: ${m.slug})\n` + body;
    }
    for (const m of postRefs.slice(CAP)) {
      ctx += `\n## Referenced post (id: ${m.slug})\n${m.name}\n`;
    }
    // The post the user is looking at, in full — unchanged.
    if (CURRENT_POST) {
      ctx += `\n## Post currently open (id: ${CURRENT_POST.id})\n`
           + "Use this id with `update-post` to fix it. Full content:\n```json\n"
           + JSON.stringify({ slot: CURRENT_POST.slot, brief: CURRENT_POST.brief }, null, 2)
           + "\n```\n";
    }
    if (attachedFiles.length) {
      ctx += "\n## Attached files\n" + attachedFiles.map(f =>
        `### ${f.name}\n\`\`\`\n${f.content}\n\`\`\``
      ).join("\n\n");
    }
    return ctx;
  }
```

- [ ] **Step 2: Await it in `send`**

At `dashboard/app.js:1357`, change:

```javascript
    const ctx = await buildContext(text);
```

(`send` is already `async`, so this is the only call-site change.)

- [ ] **Step 3: Manual verify — single post**

In chat, while NOT on a post detail page, type `@<some-post-id> what's wrong with this caption?` and send. Expected: the request `context` (visible via devtools Network → `/api/ask` payload) contains a `## Referenced post (id: …)` block with the post's slot+brief JSON.

- [ ] **Step 4: Manual verify — dedupe + cap**

While ON a post detail page (so `CURRENT_POST` is set), `@`-mention that same post: expected NO duplicate block (only the `## Post currently open` block appears). `@`-mention 6 distinct posts in one message: expected 5 full `Referenced post` blocks + 1 id/label-only block.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: inline @-referenced post content into chat context (cap 5, dedupe)"
```

---

## Self-Review

**Spec coverage:**
- "Add `GET /api/posts-index` across all profiles" → Task 1 (backed by `db.posts()`, which already aggregates all profiles).
- "Client fetches once, caches beside `_TREE`" → Task 2 Steps 1-2 (`_POSTS` global, fetched in `renderRail` alongside `_TREE`). Note: refreshed on every `renderRail` rather than literally once, so newly created posts become mentionable without a reload — a strict improvement over "once".
- "`mentionCandidates()` appends posts; ICON gains `post`" → Task 2 Steps 3-4.
- "`buildContext` async, inline full slot+brief, cap 5, dedupe with CURRENT_POST" → Task 3 Step 1.
- "`send` already awaits it" → Task 3 Step 2.

**Deviation from spec (intentional):** Spec listed a `dashboard/fileops.py` post-index helper. `db.posts()` already returns the exact data shape across all profiles, so the endpoint reuses it and `fileops.py` is untouched. Recorded in Global Constraints.

**Placeholder scan:** No TBD/TODO. All code steps show full code. Manual-verify steps replace unit tests for the two JS-only tasks (no JS test harness exists in this repo — tests dir is Python `unittest` only); the Python-testable surface (the endpoint's data contract) is covered by Task 1.

**Type consistency:** candidate object keys `{type, slug, name, meta}` consistent across `mentionCandidates`/`openMenu`/`pickMention`. Post mention `type:"post"`, `slug:<id>` consistent between Task 2 (push) and Task 3 (filter on `m.type === "post"`, fetch `"/api/post/" + m.slug`). `/api/post/{id}` returns `{slot, brief}` — matches the `JSON.stringify({slot, brief})` shape used for `CURRENT_POST`.
