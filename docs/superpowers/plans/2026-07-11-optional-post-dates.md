# Optional Post Dates + Unscheduled Bucket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make post `date` opt-in at generation time, block publishing an undated post, let non-published posts have their date cleared, and add a global "Unscheduled" nav view listing every undated, non-published post across all profiles.

**Architecture:** Backend (`generate.py`, `dashboard/fileops.py`, `dashboard/osctl.py`) gets a threaded `assign_dates`/`--dates`/`dates` opt-in flag and two validation guards on the existing status-transition and post-update paths. Frontend (`dashboard/app.js`) adds a checkbox to the existing Generate Ideas form, a shared `nextActionFor()` helper that both existing post-list renderers and a new `renderUnscheduled()` view use to gate the Publish action in the UI, and a "Clear date" control on the post-edit form. No new API endpoints — the Unscheduled view reuses the already-loaded `/api/posts-index` data (`_POSTS`).

**Tech Stack:** Python 3 (stdlib `unittest`, `argparse`), vanilla JS (no build step, no JS test suite in this repo — frontend changes are verified manually in the browser per project convention).

## Global Constraints

- Public repo: never write real venture/profile/product names into tracked files (tests, fixtures, docs). Use generic slugs only (`acme`, `demo`) — every existing test in this repo already follows this; match it.
- Backend changes are TDD (failing test → minimal implementation → passing test) per existing `tests/*.py` patterns (stdlib `unittest`, one test class per file, `setUp`/`tearDown` build a temp workspace via `tests/test_index_projects.write`).
- Frontend changes have no automated test coverage in this repo — verify manually by running `python3 dashboard/server.py` (default `http://127.0.0.1:8765`) and exercising the flow in a browser, per this project's CLAUDE.md UI-testing rule.
- Run the full suite (`python -m unittest discover tests`) after each backend task before committing.

---

### Task 1: `do_plan` — dates opt-in, defense-in-depth strip

**Files:**
- Modify: `generate.py:363-459` (`do_plan`)
- Modify: `prompts/plan.txt`
- Test: `tests/test_generate_plan.py`

**Interfaces:**
- Consumes: nothing new (existing `run_job`, `channel_slug_map`, `mint_post_ids`, `_assign_split_ids`).
- Produces: `do_plan(root, profile_slug, period, platforms, cadence, focus, brief_counts=None, voice_counts=None, assign_dates=False)` — new trailing keyword `assign_dates`, default `False`. When `False`, no post written to `content/plan-*.json` carries a `date` key, regardless of what the model returned.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generate_plan.py` (new test methods on `DoPlanTest`):

```python
    def test_default_strips_dates_even_if_model_emits_them(self):
        # assign_dates defaults to False — a fresh plan must come out unscheduled
        # even if the model ignores the instruction and includes a date anyway.
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertNotIn("date", post)

    def test_assign_dates_true_keeps_model_dates(self):
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          assign_dates=True)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["date"], "2026-07-01")

    def test_prompt_reflects_date_assignment_flag(self):
        captured = {}
        def fake_run_job(prompt, voice, validate, **k):
            captured["prompt"] = prompt
            return {"period": "p", "profile": "demo", "posts": []}
        generate.run_job = fake_run_job
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        self.assertIn("Do NOT include a \"date\" field", captured["prompt"])
        captured.clear()
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          assign_dates=True)
        self.assertIn("Assign each post a realistic date", captured["prompt"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_generate_plan -v`
Expected: `test_default_strips_dates_even_if_model_emits_them` FAILs (`date` key present), `test_assign_dates_true_keeps_model_dates` FAILs with `TypeError: do_plan() got an unexpected keyword argument 'assign_dates'`, `test_prompt_reflects_date_assignment_flag` FAILs (`AssertionError`, text not in prompt).

- [ ] **Step 3: Implement**

In `generate.py`, change the `do_plan` signature (line 363-364):

```python
def do_plan(root: Path, profile_slug: str, period: str, platforms, cadence, focus,
            brief_counts: dict | None = None, voice_counts: dict | None = None,
            assign_dates: bool = False):
```

In the `params` block (lines 385-394), insert a DATE ASSIGNMENT section right after `focus`:

```python
    params = (
        "\n\n--- PARAMETERS ---\n"
        f"profile-slug: {profile_slug}\n"
        f"period: {period}\n"
        f"platforms: {', '.join(platforms)}\n"
        f"cadence (posts per platform per week): {cadence}\n"
        f"focus: {focus or '(none)'}\n"
        "\n--- DATE ASSIGNMENT ---\n"
        + ("Assign each post a realistic date (YYYY-MM-DD), spread sensibly across the period.\n"
           if assign_dates else
           "Do NOT include a \"date\" field on any post — this batch is unscheduled; "
           "the user will assign dates later.\n")
        + "\n--- RECENT HISTORY (do not repeat) ---\n"
        f"{recent_history(content_dir)}\n"
    )
```

In the post-normalization loop (lines 429-440), add the strip after the existing `format` default:

```python
    for post in obj.get("posts", []):
        post["channels"] = [
            ch if ch in valid else cmap.get(str(ch).lower(), ch)
            for ch in post.get("channels", [])
        ]
        post["status"] = "planned"
        if not post.get("format"):
            post["format"] = "carousel"
        if not assign_dates:
            post.pop("date", None)
```

In `prompts/plan.txt`, add a bullet to the Rules list (after the "Respect the parameters block..." line, before "Do not repeat concepts..."):

```
- Whether posts get a `date` is controlled by the DATE ASSIGNMENT note in the
  parameters block below. When told not to assign dates, omit the `date` key
  from every post object entirely — do not guess a placeholder date.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_generate_plan -v`
Expected: all PASS, including the 4 pre-existing tests in the file (no regressions — they all call `do_plan` without `assign_dates`, which now defaults to `False` and strips their `"date": "2026-07-01"` fixture values; none of those tests assert on `post["date"]`, so they're unaffected).

- [ ] **Step 5: Commit**

```bash
git add generate.py prompts/plan.txt tests/test_generate_plan.py
git commit -m "feat: make plan-generation date assignment opt-in (default off)"
```

---

### Task 2: CLI/API plumbing for `--dates` / `dates`

**Files:**
- Modify: `generate.py:648-657` (argparse `plan` subcommand), `generate.py:685-688` (`main()` dispatch)
- Modify: `dashboard/fileops.py:1535-1557` (`_plan_args`)
- Modify: `dashboard/osctl.py:416-440` (`generate-plan` subcommand)
- Test: `tests/test_fileops_plan_args.py`, `tests/test_osctl.py`

**Interfaces:**
- Consumes: `do_plan(..., assign_dates=False)` from Task 1.
- Produces: `fileops._plan_args(profile_slug, params)` appends `"--dates"` to the argv when `params.get("dates")` is truthy. `osctl generate-plan --dates` sets `params["dates"] = True`. `generate.py plan --dates` sets `args.dates = True`, forwarded as `assign_dates=args.dates`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_plan_args.py`:

```python
    def test_dates_flag_forwarded_when_set(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14",
                                            "dates": True})
        self.assertIn("--dates", args)

    def test_dates_flag_omitted_by_default(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14"})
        self.assertNotIn("--dates", args)
```

Add to `tests/test_osctl.py` (new test method on the existing class, near `test_generate_plan_delegates_to_fileops`):

```python
    def test_generate_plan_forwards_dates_flag(self):
        run(["create-project", "--slug", "acme"])
        run(["create-profile", "--project", "acme", "--slug", "demo"])
        with mock.patch.object(fileops, "run_plan",
                               return_value={"profile_slug": "demo", "stdout": "ok"}) as plan:
            run(["generate-plan", "--profile", "demo",
                 "--period", "2026-07-01 to 2026-07-14", "--dates"])
        plan.assert_called_once_with("demo", {
            "period": "2026-07-01 to 2026-07-14",
            "dates": True,
        })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_fileops_plan_args tests.test_osctl -v`
Expected: `test_dates_flag_forwarded_when_set` FAILs (`--dates` not in args), `test_generate_plan_forwards_dates_flag` FAILs with `argparse` error (`unrecognized arguments: --dates`). `test_dates_flag_omitted_by_default` already passes (no code change needed for it, it's a regression guard).

- [ ] **Step 3: Implement**

In `generate.py`, add to the `plan` subparser (after line 653, `--focus`):

```python
    pp.add_argument("--dates", action="store_true",
                    help="assign a date to each minted post, spread across the period "
                         "(default: leave every post unscheduled)")
```

In `generate.py` `main()`, update the `plan` dispatch (line 687-688):

```python
        if args.job == "plan":
            platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
            do_plan(root, args.profile, args.period, platforms, args.cadence, args.focus,
                    _parse_counts(args.brief_counts), _parse_counts(args.voice_counts),
                    assign_dates=args.dates)
```

In `dashboard/fileops.py` `_plan_args`, add before the `return args` (after the `voice_counts` block, line 1554-1556):

```python
    if params.get("dates"):
        args += ["--dates"]
    return args
```

In `dashboard/osctl.py`, add to the `generate-plan` subparser (after line 426, `--voice-counts`):

```python
    p.add_argument("--dates", action="store_true",
                   help="assign a date to each post (default: leave unscheduled)")
```

And in `_generate_plan` (after the `voice_counts` block, line 437-438):

```python
        if a.dates:
            params["dates"] = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fileops_plan_args tests.test_osctl -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add generate.py dashboard/fileops.py dashboard/osctl.py tests/test_fileops_plan_args.py tests/test_osctl.py
git commit -m "feat: wire --dates flag through generate-plan CLI and API"
```

---

### Task 3: Publish gate — `set_status` requires a date

**Files:**
- Modify: `dashboard/fileops.py:282-298` (`set_status`)
- Test: `tests/test_fileops_posts.py`

**Interfaces:**
- Consumes: `fileops.add_post`, `fileops.set_status`, `fileops.update_post` (all existing).
- Produces: `set_status(post_id, "published", ...)` raises `ActionError` when the post has no `date`, regardless of caller (dashboard, chat, CLI all funnel through this one function).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_posts.py` (new methods on class `T`):

```python
    def test_publish_without_date_raises(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved"):
            fileops.set_status(pid, to)
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.set_status(pid, "published")
        self.assertIn("add a date first", str(ctx.exception))
        self.assertEqual(db.profile_posts("demo")[0]["status"], "approved")

    def test_publish_with_date_succeeds(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved"):
            fileops.set_status(pid, to)
        fileops.set_status(pid, "published")
        self.assertEqual(db.profile_posts("demo")[0]["status"], "published")

    def test_non_publish_transitions_unaffected_by_missing_date(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "rejected"):
            fileops.set_status(pid, to)  # must not raise at any step
        self.assertEqual(db.profile_posts("demo")[0]["status"], "rejected")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_fileops_posts -v`
Expected: `test_publish_without_date_raises` FAILs (no `ActionError` raised, status becomes `published`). The other two already pass (regression guards).

- [ ] **Step 3: Implement**

In `dashboard/fileops.py` `set_status`, add the guard after the transition-table check and before the write (line 293-295):

```python
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ActionError(
            f"illegal transition {current} -> {new_status}"
            f" (allowed: {sorted(ALLOWED_TRANSITIONS.get(current, set())) or 'none'})"
        )
    if new_status == "published" and not ctx["post"].get("date"):
        raise ActionError(f"cannot publish '{post_id}' — add a date first")
    ctx["post"]["status"] = new_status
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fileops_posts -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_posts.py
git commit -m "fix: block publishing a post that has no date"
```

---

### Task 4: Clear/change date guard on published posts

**Files:**
- Modify: `dashboard/fileops.py:594-609` (`update_post`)
- Test: `tests/test_fileops_posts.py`

**Interfaces:**
- Consumes: `fileops.update_post(post_id, fields, profile_slug=None)` (existing signature, unchanged).
- Produces: `update_post` raises `ActionError` only when `fields["date"]` (after stripping) actually differs from the post's current stored date AND the post's status is `published`. Saving unrelated fields on a published post, with the date field present-but-unchanged (as the edit form always sends it), still succeeds.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_posts.py`:

```python
    def test_clear_date_on_non_published_post_succeeds(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        fileops.update_post(pid, {"date": ""})
        slot = fileops.read_detail(pid)["slot"]
        self.assertNotIn("date", slot)

    def test_change_date_on_published_post_raises(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "published"):
            fileops.set_status(pid, to)
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.update_post(pid, {"date": ""})
        self.assertIn("cannot change the date of a published post", str(ctx.exception))
        self.assertEqual(fileops.read_detail(pid)["slot"]["date"], "2026-07-15")

    def test_unchanged_date_on_published_post_does_not_raise(self):
        # The edit form always submits the date field, even when the user only
        # touched another field — an unchanged value must not trip the guard.
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok",
                                  "date": "2026-07-15"})
        pid = db.profile_posts("demo")[0]["id"]
        for to in ("approved_slot", "briefed", "approved", "published"):
            fileops.set_status(pid, to)
        fileops.update_post(pid, {"date": "2026-07-15", "pillar": "curiosity"})
        slot = fileops.read_detail(pid)["slot"]
        self.assertEqual(slot["date"], "2026-07-15")
        self.assertEqual(slot["pillar"], "curiosity")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_fileops_posts -v`
Expected: `test_change_date_on_published_post_raises` FAILs (no exception, date silently cleared). The other two already pass (regression guards — importantly confirming the naive "block whenever 'date' in fields" approach would have broken `test_unchanged_date_on_published_post_does_not_raise`, which is why the guard compares values).

- [ ] **Step 3: Implement**

In `dashboard/fileops.py` `update_post`, add the guard right after `ctx = find_post(...)` (line 596):

```python
def update_post(post_id, fields, profile_slug=None):
    """Edit plan-slot fields and, when a brief exists, patch brief JSON in one save."""
    ctx = find_post(post_id, profile_slug)
    if "date" in fields:
        new_date = (fields.get("date") or "").strip()
        if new_date != (ctx["post"].get("date") or "") and ctx["post"].get("status") == "published":
            raise ActionError("cannot change the date of a published post")
    for k in _POST_FIELDS:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fileops_posts -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_posts.py
git commit -m "fix: lock a published post's date against accidental clear/change"
```

---

### Task 5: Frontend — shared publish-gate helper wired into existing post views

**Files:**
- Modify: `dashboard/app.js:1104-1227` (`STAGE_GROUP`/`STATUS_PILL_CLASS`/`NEXT` consts, `renderProfile`'s `drawList`/`doNext`)
- Modify: `dashboard/app.js:1597-1648` (`renderPostDetail`)

**Interfaces:**
- Consumes: `NEXT` map (existing), post objects with `.status` and `.date`.
- Produces: `nextActionFor(p)` → `null` (no action available) or `{label, blocked, to, brief}`. `blocked: true` means clicking the action must navigate to the edit form instead of calling the API. Task 7's `renderUnscheduled()` reuses this exact function — do not inline the logic elsewhere.

- [ ] **Step 1: Add the helper**

In `dashboard/app.js`, right after the `NEXT` const (line 1107-1111), add:

```js
// Wraps NEXT with the publish-requires-a-date rule: an approved, undated post
// still shows an action button, but it routes to the edit form instead of
// firing the publish transition. Shared by every view that renders a post's
// next-action button (profile list, post detail, Unscheduled bucket).
function nextActionFor(p){
  const n = NEXT[p.status];
  if(!n) return null;
  if(p.status==="approved" && !p.date) return {label:"Add date to publish", blocked:true};
  return {label:n.label, blocked:false, to:n.to, brief:n.brief};
}
```

- [ ] **Step 2: Wire into `renderProfile`'s `drawList`/`doNext`**

Replace (line 1176-1177 inside `drawList`'s `.map`):

```js
      const pk=STATUS_PILL_CLASS[p.status]||"idea";
      const n=NEXT[p.status];
```

with:

```js
      const pk=STATUS_PILL_CLASS[p.status]||"idea";
      const na=nextActionFor(p);
```

Replace (line 1189):

```js
        ${n?`<button class="go" data-act="${p.id}">${n.label}</button>`:""}
```

with:

```js
        ${na?`<button class="go" data-act="${p.id}">${esc(na.label)}</button>`:""}
```

Replace `doNext` (lines 1199-1203):

```js
  function byId(id){ return posts.find(p=>p.id===id)||{}; }
  async function doNext(id){ const p=byId(id), n=NEXT[p.status]; if(!n) return;
    try{ if(n.brief){ toast("Writing via claude -p… (a few seconds)"); await api(postUrl(id,slug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else { await api(postUrl(id,slug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
      renderProfile(slug); renderRail(); }catch(e){ toast("✗ "+e.message); } }
```

with:

```js
  function byId(id){ return posts.find(p=>p.id===id)||{}; }
  async function doNext(id){ const p=byId(id), na=nextActionFor(p); if(!na) return;
    if(na.blocked){ return navigate(`#/post/${id}/edit`,{profileSlug:slug}); }
    try{ if(na.brief){ toast("Writing via claude -p… (a few seconds)"); await api(postUrl(id,slug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else { await api(postUrl(id,slug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:na.to})}); toast("✓ "+plainStatus(na.to)); }
      renderProfile(slug); renderRail(); }catch(e){ toast("✗ "+e.message); } }
```

- [ ] **Step 3: Wire into `renderPostDetail`**

Replace (line 1606):

```js
  const st=slot.status||"planned", n=NEXT[st];
```

with:

```js
  const st=slot.status||"planned", na=nextActionFor(slot);
```

Replace (line 1619, inside the `btns` array):

```js
    n?`<button class="btn primary" id="pd-next">${esc(n.label)}</button>`:"",
```

with:

```js
    na?`<button class="btn primary" id="pd-next">${esc(na.label)}</button>`:"",
```

Replace the `pd-next` handler (lines 1641-1647):

```js
  const nb=document.getElementById("pd-next"); if(nb) nb.onclick=async()=>{
    nb.disabled=true;
    try{ if(n.brief){ toast("Writing via claude -p…",true); await api(postUrl(id,profileSlug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else{ await api(postUrl(id,profileSlug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
      navigate(`#/post/${id}`,{profileSlug}); }
    catch(e){ nb.disabled=false; toast("✗ "+e.message); }
  };
```

with:

```js
  const nb=document.getElementById("pd-next"); if(nb) nb.onclick=async()=>{
    if(na.blocked){ return navigate(`#/post/${id}/edit`,{profileSlug}); }
    nb.disabled=true;
    try{ if(na.brief){ toast("Writing via claude -p…",true); await api(postUrl(id,profileSlug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else{ await api(postUrl(id,profileSlug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:na.to})}); toast("✓ "+plainStatus(na.to)); }
      navigate(`#/post/${id}`,{profileSlug}); }
    catch(e){ nb.disabled=false; toast("✗ "+e.message); }
  };
```

- [ ] **Step 4: Manual verification**

Run: `python3 dashboard/server.py` (starts on `http://127.0.0.1:8765`), open it in a browser.
1. Open a profile with a post at "approved" status and no date. Confirm the list row's action button reads "Add date to publish" and clicking it opens the edit form (not a status-change API call — check no toast fires, no network request to `/status`).
2. On the post's detail page, confirm the primary button also reads "Add date to publish" and behaves the same way.
3. Add a date to that post via the edit form, save, and confirm the button reverts to "Publish →" in both the list and detail views, and clicking it now publishes successfully.
4. Confirm a "briefed" post (no date) still shows "Review →" and works normally — only the `approved → published` step is gated.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: gate the Publish action in the UI when a post has no date"
```

---

### Task 6: Frontend — dates checkbox on Generate Ideas + Clear-date on Edit Post

**Files:**
- Modify: `dashboard/app.js:2014-2042` (`renderGenerateIdeas`)
- Modify: `dashboard/app.js:1650-1684` (`renderEditPost`)

**Interfaces:**
- Consumes: `params["dates"]` accepted by `POST /api/profile/<slug>/plan` (Task 2), `update_post` guard (Task 4).
- Produces: no new exported interfaces — purely UI.

- [ ] **Step 1: Add the checkbox to Generate Ideas**

In `dashboard/app.js` `renderGenerateIdeas`, replace the form body (lines 2026-2030):

```js
      ${flabel("Period start")}${finput("period_start",isoDay(start),'type="date" required')}
      ${flabel("Period end")}${finput("period_end",isoDay(end),'type="date" required')}
      ${flabel("Platforms")}${finput("platforms",channels.map(c=>c.platform).join(","),'placeholder="tiktok,instagram"')}
      ${flabel("Cadence (posts per platform / week)")}${finput("cadence","",'placeholder="3"')}
      ${flabel("Focus (optional)")}${finput("focus","",'placeholder="push the launch"')}
```

with:

```js
      ${flabel("Period start")}${finput("period_start",isoDay(start),'type="date" required')}
      ${flabel("Period end")}${finput("period_end",isoDay(end),'type="date" required')}
      <div style="display:flex;align-items:center;gap:8px;margin:2px 0 16px">
        <input type="checkbox" id="gi-dates" style="width:16px;height:16px;cursor:pointer">
        <label for="gi-dates" style="font-size:13px;color:var(--ink2);cursor:pointer">Assign dates to posts (spread across the period above)</label>
      </div>
      ${flabel("Platforms")}${finput("platforms",channels.map(c=>c.platform).join(","),'placeholder="tiktok,instagram"')}
      ${flabel("Cadence (posts per platform / week)")}${finput("cadence","",'placeholder="3"')}
      ${flabel("Focus (optional)")}${finput("focus","",'placeholder="push the launch"')}
```

Replace the save handler's payload build (line 2035):

```js
    const payload={period:`${data.period_start} to ${data.period_end}`,platforms:data.platforms,cadence:data.cadence,focus:data.focus};
```

with:

```js
    const payload={period:`${data.period_start} to ${data.period_end}`,platforms:data.platforms,cadence:data.cadence,focus:data.focus};
    if(document.getElementById("gi-dates").checked) payload.dates = true;
```

- [ ] **Step 2: Add Clear-date to Edit Post**

In `dashboard/app.js` `renderEditPost`, replace the date field line (line 1665):

```js
      ${flabel("Date")}${finput("date",slot.date||"",'type="date"')}
```

with:

```js
      ${flabel("Date")}<div style="display:flex;gap:8px;align-items:center">${finput("date",slot.date||"",`type="date"${slot.status==="published"?" disabled":""}`)}${slot.status!=="published"?`<button type="button" class="btn" id="ep-clear-date" style="flex:none">Clear date</button>`:""}</div>
```

After the `document.getElementById("ep-save").onclick=...` block (after line 1682, before `document.getElementById("ep-del")...`), add:

```js
  const clearDateBtn=document.getElementById("ep-clear-date");
  if(clearDateBtn) clearDateBtn.onclick=()=>{ $("#main input[name=date]").value=""; };
```

- [ ] **Step 3: Manual verification**

Run: `python3 dashboard/server.py`, open in browser.
1. Open "Generate ideas" on any profile. Confirm the "Assign dates to posts" checkbox is present and **unchecked** by default. Generate a small batch (leave unchecked) — confirm the resulting ideas show no date in the profile list (the `small` subtitle line shows no trailing date).
2. Generate again with the checkbox checked — confirm the new posts do show a date.
3. Open a non-published post's Edit form. Confirm a "Clear date" button appears next to the Date field; click it, then Save; confirm the post now shows no date in the list.
4. Open a published post's Edit form. Confirm the Date field is disabled (greyed out, not editable) and no "Clear date" button is present. Change another field (e.g. Pillar) and Save — confirm it saves without error (regression check for the Task 4 unchanged-date fix).

- [ ] **Step 4: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: opt-in date checkbox on Generate Ideas, Clear-date on Edit Post"
```

---

### Task 7: Frontend — "Unscheduled" global nav view

**Files:**
- Modify: `dashboard/app.js:184-217` (`ROUTES`)
- Modify: `dashboard/app.js:402-405` (`renderRail` nav markup)
- Modify: `dashboard/app.js:449-458` (`refreshViews`)
- Modify: `dashboard/app.js` — add new function `renderUnscheduled` (place it after `writeAllIdeas`, i.e. after line 1255, before `function selectProfileSetup`)

**Interfaces:**
- Consumes: `_POSTS` (global, refreshed by `renderRail()` on every call — already the case before this task), `nextActionFor` (Task 5), `STAGE_GROUP`, `STATUS_PILL_CLASS`, `NEXT`, `plainStatus`, `postUrl`, `api`, `toast`, `navigate`, `esc`, `$` (all pre-existing).
- Produces: `renderUnscheduled()` — no return value, renders into `#main`. Route `#/unscheduled`.

- [ ] **Step 1: Add the nav link**

In `dashboard/app.js` `renderRail`, replace (lines 402-405):

```js
    <nav class="nav">
      <a data-view="needs"><span class="ico">◉</span> Needs you</a>
      <a data-view="calendar"><span class="ico">▦</span> Calendar</a>
      <a data-view="operations"><span class="ico">✓</span> Operations</a>
    </nav>
```

with:

```js
    <nav class="nav">
      <a data-view="needs"><span class="ico">◉</span> Needs you</a>
      <a data-view="calendar"><span class="ico">▦</span> Calendar</a>
      <a data-view="unscheduled"><span class="ico">◷</span> Unscheduled</a>
      <a data-view="operations"><span class="ico">✓</span> Operations</a>
    </nav>
```

- [ ] **Step 2: Add the route**

In `dashboard/app.js` `ROUTES`, add a new entry right after the `needs` route (line 188):

```js
  [/^\/needs$/,                                 ()       => { setState("needs"); renderNeeds(); }],
  [/^\/unscheduled$/,                           ()       => { setState("unscheduled"); renderUnscheduled(); }],
```

- [ ] **Step 3: Add the `refreshViews` branch**

In `dashboard/app.js` `refreshViews`, add a branch (after the `operations` branch, line 453):

```js
  if (v === "calendar") return renderTimeline();
  if (v === "operations") return renderOperations();
  if (v === "unscheduled") return renderUnscheduled();
```

- [ ] **Step 4: Implement `renderUnscheduled`**

Add this function after `writeAllIdeas` (after line 1255):

```js
// Cross-profile bucket: every non-published post with no date, grouped by
// profile. Reuses the already-loaded _POSTS index (no new API call) and the
// same nextActionFor() publish gate as the profile list / post detail views.
async function renderUnscheduled(){
  const rows = _POSTS.filter(p=>p.status!=="published" && !p.date);
  let FILTER = "all";
  const count = g => rows.filter(p=>STAGE_GROUP[p.status]===g).length;
  $("#main").innerHTML = `<div class="topbar"><div><div class="crumbs">Across everything</div><h1 class="title">Unscheduled</h1></div></div>
    <div style="padding:0 24px 8px;font-size:12px;color:var(--dim)">${rows.length} posts with no date</div>
    <div class="scroll">
      <div class="filters">
        <span class="chip on" data-f="all">All <span class="n">${rows.length}</span></span>
        <span class="chip" data-f="ideas">💡 Ideas <span class="n">${count("ideas")}</span></span>
        <span class="chip" data-f="drafts">✍ Drafts <span class="n">${count("drafts")}</span></span>
      </div>
      <div id="uns-list"></div>
    </div>`;

  function drawList(){
    const visible = rows.filter(p=>FILTER==="all"||STAGE_GROUP[p.status]===FILTER);
    const el = $("#uns-list");
    if(!visible.length){ el.innerHTML=`<div style="padding:24px 4px;color:var(--dim)">Nothing unscheduled.</div>`; return; }
    const bySlug = {};
    visible.forEach(p=>{ (bySlug[p.profile_slug]=bySlug[p.profile_slug]||[]).push(p); });
    const slugs = Object.keys(bySlug).sort((a,b)=>
      (bySlug[a][0].profile_name||a).localeCompare(bySlug[b][0].profile_name||b));
    el.innerHTML = slugs.map(slug=>{
      const g = bySlug[slug], name = g[0].profile_name||slug;
      const rowsHtml = g.map(p=>{
        const pk=STATUS_PILL_CLASS[p.status]||"idea";
        const na=nextActionFor(p);
        const title = p.working_title || p.pillar || p.id;
        const isIdea = p.status==="planned"||p.status==="approved_slot";
        const sub = isIdea ? (p.concept || "Just an idea — not written yet") : (p.brief_path?"Written — click to view":"");
        return `<div class="post">
          <span class="stp ${pk}">${esc(plainStatus(p.status))}</span>
          <div class="t" data-view="${p.id}" data-slug="${esc(slug)}" style="cursor:pointer;min-width:0">${esc(title)}<small>${esc(sub)}</small></div>
          ${na?`<button class="go" data-act="${p.id}" data-slug="${esc(slug)}">${esc(na.label)}</button>`:""}
          <button class="more" data-menu="${p.id}" data-slug="${esc(slug)}">Edit</button></div>`;
      }).join("");
      return `<div class="pcard" style="margin-bottom:14px">
        <div style="font:700 12px/1 var(--body);color:var(--ink2);margin-bottom:8px;cursor:pointer" data-profile-jump="${esc(slug)}">${esc(name)}</div>
        <div class="rowc">${rowsHtml}</div></div>`;
    }).join("");
    el.querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{
      const id=b.dataset.act, slug=b.dataset.slug, p=rows.find(r=>r.id===id), na=p?nextActionFor(p):null;
      if(!na) return;
      if(na.blocked){ return navigate(`#/post/${id}/edit`,{profileSlug:slug}); }
      try{ if(na.brief){ toast("Writing via claude -p… (a few seconds)"); await api(postUrl(id,slug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
        else{ await api(postUrl(id,slug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:na.to})}); toast("✓ "+plainStatus(na.to)); }
        renderRail(); renderUnscheduled(); }catch(e){ toast("✗ "+e.message); }
    });
    el.querySelectorAll("[data-menu]").forEach(b=>b.onclick=()=>navigate(`#/post/${b.dataset.menu}/edit`,{profileSlug:b.dataset.slug}));
    el.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>navigate(`#/post/${b.dataset.view}`,{profileSlug:b.dataset.slug}));
    el.querySelectorAll("[data-profile-jump]").forEach(b=>b.onclick=()=>navigate(`#/profile/${b.dataset.profileJump}`));
  }
  $("#main").querySelectorAll(".chip").forEach(c=>c.onclick=()=>{ FILTER=c.dataset.f;
    $("#main").querySelectorAll(".chip").forEach(x=>x.classList.toggle("on",x===c)); drawList(); });
  drawList();
}
```

- [ ] **Step 5: Manual verification**

Run: `python3 dashboard/server.py`, open in browser.
1. Confirm "Unscheduled" appears in the left nav between Calendar and Operations, with a clock icon.
2. Click it — confirm it lands on `#/unscheduled`, header reads "Unscheduled" with an "N posts with no date" count, and every profile with undated ideas/drafts appears as its own group.
3. Confirm a profile with zero undated posts does NOT appear in the list.
4. Click the All/Ideas/Drafts filter chips — confirm the list narrows correctly and the count badges match.
5. Click a post's title — confirm it opens that post's detail page (correct profile context, "← Back" returns correctly).
6. Click "Write it →" on an idea-stage row — confirm it briefs successfully and the row either updates to Draft or disappears from an active Ideas-only filter, matching the filter's semantics.
7. Click an approved+undated row's "Add date to publish" button — confirm it opens that post's edit form (not a failed publish call).
8. Click the profile-name group header — confirm it navigates to that profile's page.
9. Add a date to one of the listed posts and confirm it disappears from the Unscheduled view on next visit (re-navigate away and back, or trigger `refreshViews` via any chat mutation).

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: add global Unscheduled nav view for undated non-published posts"
```
