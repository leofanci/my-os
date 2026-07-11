# CRUD parity for memos, experiments, and roadmap features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give memos, experiments, and roadmap features the same edit + delete capability posts/milestones/projects already have — same osctl-only write path, same dashboard card UI, available manually and via chat.

**Architecture:** Add `update_*`/`delete_*` functions to `dashboard/fileops.py` following the exact shape of their existing `update_experiment`/`delete_activity`/`delete_milestone` siblings, expose them as new `osctl` subcommands, wire direct-branch HTTP routes in `dashboard/server.py` (matching the style already used for posts/milestones), then add ✎/🗑 buttons to the three card renderers in `dashboard/app.js` that reuse the existing schema-driven "New X" forms (now prefillable) and the existing `renderConfirmDelete`-style modal flow.

**Tech Stack:** Python stdlib (`http.server`, `argparse`, `json`), vanilla JS (no framework), existing `unittest` test suite.

## Global Constraints

- Repo is public: **never** write real venture/profile/product names into tracked files (tests, code, docs). Use generic slugs (`acme`, `demo`) — matches every existing test fixture in `tests/`.
- All content mutations go through `dashboard/fileops.py` functions called from `dashboard/osctl.py` — never write JSON/markdown files directly from `server.py` or `app.js`.
- Every new backend function must raise `fileops.ActionError` (not a bare exception) for "not found" / invalid-input cases — this is what `osctl.main` and `server.py`'s `except fileops.ActionError` branch expect for clean 404s/CLI error JSON.
- Every file mutation ends with `reindex()` — this is what keeps `os.db` (the read side) in sync with the files (the write side / source of truth).
- Memos are versioned (`<type>-v<N>.json`); `update_memo` patches the **specific version already on disk**, in place — it does not create a new version. `create_memo` is untouched and still always creates the next version.
- Run `python -m pytest tests/test_no_usage_data.py` before considering any task done — the public-repo guard test.

---

### Task 1: fileops — memo update + delete

**Files:**
- Modify: `dashboard/fileops.py` (add two functions after `create_memo`, which ends at line 1328)
- Test: `tests/test_fileops_crud.py`

**Interfaces:**
- Produces: `fileops.update_memo(project_slug: str, memo_type: str, version: int, fields: dict) -> dict` returning `{"id", "type", "version", "path", "project"}`
- Produces: `fileops.delete_memo(project_slug: str, memo_type: str, version: int) -> dict` returning `{"type", "version", "project", "deleted": True}`
- Consumes: `MEMO_TYPES`, `normalize_memo_body`, `dumps_json` (already imported in fileops.py from `core.project_schemas`), `lk_memo` (already imported from `core.ids`), module-local `_project_dir`, `_composed_id`, `ActionError`, `reindex`, `ROOT`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_crud.py`, inside `class CrudTest`, after `test_timeline_milestone_carries_ref_id`:

```python
    # ---- memo ---------------------------------------------------------------- #
    def test_update_memo_patches_fields_in_place_same_version(self):
        created = fileops.create_memo("acme", "assessment", {
            "pace_recommendation": "accelerate",
            "riskiest_assumption": "people will pay",
        })
        self.assertEqual(created["version"], 1)
        fileops.update_memo("acme", "assessment", 1, {"pace_recommendation": "validate quietly"})
        proj = db.project("acme")
        memo = next(m for m in proj["memos"] if m["type"] == "assessment" and m["version"] == 1)
        body = json.loads((self.root / memo["file_path"]).read_text())
        self.assertEqual(body["pace_recommendation"], "validate quietly")
        # untouched field survives the patch
        self.assertEqual(body["riskiest_assumption"], "people will pay")

    def test_update_memo_unknown_version_raises(self):
        fileops.create_memo("acme", "assessment", {"pace_recommendation": "accelerate"})
        with self.assertRaises(fileops.ActionError):
            fileops.update_memo("acme", "assessment", 9, {"pace_recommendation": "x"})

    def test_delete_memo_removes_the_version_file(self):
        fileops.create_memo("acme", "assessment", {"pace_recommendation": "accelerate"})
        fileops.delete_memo("acme", "assessment", 1)
        proj = db.project("acme")
        self.assertFalse([m for m in proj["memos"] if m["type"] == "assessment" and m["version"] == 1])

    def test_delete_memo_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_memo("acme", "assessment", 9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fileops_crud.py -k memo -v`
Expected: FAIL with `AttributeError: module 'dashboard.fileops' has no attribute 'update_memo'`

- [ ] **Step 3: Implement `update_memo` and `delete_memo`**

Insert into `dashboard/fileops.py` immediately after `create_memo` (after the line `return {"id": _composed_id(key), "type": mtype, "version": version, "path": rel, "project": project_slug}` that closes it, i.e. right before `def create_experiment`):

```python
def update_memo(project_slug: str, memo_type: str, version: int, fields: dict) -> dict:
    """Patch an existing memo version JSON in place (same version, not a new one)."""
    mtype = (memo_type or "").strip()
    if mtype not in MEMO_TYPES:
        raise ActionError(f"unknown memo type '{mtype}'")
    memo_dir = _project_dir(project_slug) / "strategy" / "memos"
    path = memo_dir / f"{mtype}-v{int(version)}.json"
    if not path.exists():
        raise ActionError(f"memo '{mtype}' v{version} not found")
    existing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict):
        raise ActionError(f"memo '{mtype}' v{version} is not a JSON object")
    merged = dict(existing)
    if fields:
        merged.update({k: v for k, v in fields.items() if v is not None})
    body = normalize_memo_body(mtype, merged, version=int(version))
    path.write_text(dumps_json(body), encoding="utf-8")
    reindex()
    rel = str(path.relative_to(ROOT))
    return {
        "id": _composed_id(lk_memo(project_slug, mtype, int(version))),
        "type": mtype,
        "version": int(version),
        "path": rel,
        "project": project_slug,
    }


def delete_memo(project_slug: str, memo_type: str, version: int) -> dict:
    mtype = (memo_type or "").strip()
    if mtype not in MEMO_TYPES:
        raise ActionError(f"unknown memo type '{mtype}'")
    path = _project_dir(project_slug) / "strategy" / "memos" / f"{mtype}-v{int(version)}.json"
    if not path.exists():
        raise ActionError(f"memo '{mtype}' v{version} not found")
    path.unlink()
    reindex()
    return {"type": mtype, "version": int(version), "project": project_slug, "deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fileops_crud.py -k memo -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_crud.py
git commit -m "feat: add fileops.update_memo/delete_memo (in-place edit + delete)"
```

---

### Task 2: fileops — experiment update coverage + delete

`update_experiment` already exists but has zero test coverage; `delete_experiment` doesn't exist at all. Both land in one task since they share the same test fixture.

**Files:**
- Modify: `dashboard/fileops.py` (add `delete_experiment` after `update_experiment`, which ends at line 1378)
- Test: `tests/test_fileops_crud.py`

**Interfaces:**
- Produces: `fileops.delete_experiment(project_slug: str, stem: str) -> dict` returning `{"stem", "project", "deleted": True}`
- Consumes: `fileops.update_experiment` (existing, unmodified), `fileops.create_experiment` (existing), `_project_dir`, `ActionError`, `reindex`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_crud.py`:

```python
    # ---- experiment ------------------------------------------------------------ #
    def test_update_experiment_patches_fields(self):
        created = fileops.create_experiment("acme", {"assumption": "people will pay", "stem": "will-pay"})
        fileops.update_experiment("acme", "will-pay", {"success_criteria": "10 paid signups"})
        proj = db.project("acme")
        exp = next(x for x in proj["experiments"] if x["stem"] == "will-pay")
        body = json.loads((self.root / exp["file_path"]).read_text())
        self.assertEqual(body["success_criteria"], "10 paid signups")
        self.assertEqual(body["assumption"], "people will pay")  # untouched field survives
        self.assertEqual(created["stem"], "will-pay")

    def test_update_experiment_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.update_experiment("acme", "nope", {"success_criteria": "x"})

    def test_delete_experiment_removes_it(self):
        fileops.create_experiment("acme", {"assumption": "people will pay", "stem": "will-pay"})
        fileops.delete_experiment("acme", "will-pay")
        proj = db.project("acme")
        self.assertFalse([x for x in proj["experiments"] if x["stem"] == "will-pay"])

    def test_delete_experiment_unknown_raises(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_experiment("acme", "nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fileops_crud.py -k experiment -v`
Expected: first two PASS (covering existing `update_experiment`), last two FAIL with `AttributeError: ... no attribute 'delete_experiment'`

- [ ] **Step 3: Implement `delete_experiment`**

Insert into `dashboard/fileops.py` immediately after `update_experiment` (right before `def create_product`):

```python
def delete_experiment(project_slug: str, stem: str) -> dict:
    stem = (stem or "").strip()
    if not stem:
        raise ActionError("stem is required")
    path = _project_dir(project_slug) / "strategy" / "experiments" / f"{stem}.json"
    if not path.exists():
        raise ActionError(f"experiment '{stem}' not found")
    path.unlink()
    reindex()
    return {"stem": stem, "project": project_slug, "deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fileops_crud.py -k experiment -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_crud.py
git commit -m "feat: add fileops.delete_experiment; cover update_experiment with tests"
```

---

### Task 3: fileops — feature update + delete

Features live as checklist lines inside `products/<slug>/roadmap.md` (`- [ ] Title — why — priority: X` under a `## Section` heading) — there's no per-feature file. This task adds line-level find/rewrite/remove, and extracts the section-append logic `add_feature` already has into a shared helper so `update_feature`'s "move to a different section" case reuses it instead of duplicating it.

**Files:**
- Modify: `dashboard/fileops.py`:
  - Refactor `add_feature` (currently lines 1473–1501) to use a new `_append_roadmap_line` helper
  - Add `_parse_feature_line`, `_find_feature_line_index`, `update_feature`, `delete_feature`
- Test: `tests/test_fileops_crud.py`

**Interfaces:**
- Produces: `fileops.update_feature(product_slug: str, feature_id: str, fields: dict) -> dict` returning `{"id", "title", "product", "section"}` — `fields` may contain `title`, `why`, `section`, `priority`
- Produces: `fileops.delete_feature(product_slug: str, feature_id: str) -> dict` returning `{"id", "product", "deleted": True}`
- Consumes: `_product_dir`, `_roadmap_section_name`, `_write_project_doc`, `FEATURE_PRIORITIES`, `slug_key`, `lk_feature`, `_composed_id`, `ActionError`, `reindex`
- Note: a feature's composed id is `slug_key(title)` — same as `add_feature` already mints it. Renaming a feature via `update_feature` changes its id; nothing else in the codebase persists a feature id across a rename, so this is safe.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fileops_crud.py`:

```python
    # ---- feature ------------------------------------------------------------- #
    def _make_product_with_feature(self):
        fileops.create_product("acme", "app", {"name": "Acme App"})
        fileops.add_feature("app", {"title": "Dark mode", "why": "user request", "priority": "high"})

    def test_update_feature_patches_why_and_priority_in_place(self):
        self._make_product_with_feature()
        out = fileops.update_feature("app", "dark-mode", {"why": "top request", "priority": "critical"})
        self.assertEqual(out["title"], "Dark mode")
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertIn("Dark mode — top request — priority: critical", roadmap)

    def test_update_feature_moves_between_sections(self):
        self._make_product_with_feature()  # lands in "Next" (add_feature's default)
        fileops.update_feature("app", "dark-mode", {"section": "Later / Ideas"})
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        later_block = roadmap.split("## Later / Ideas", 1)[1]
        self.assertIn("Dark mode", later_block)
        next_block = roadmap.split("## Next", 1)[1].split("## ", 1)[0]
        self.assertNotIn("Dark mode", next_block)

    def test_update_feature_rename_changes_id(self):
        self._make_product_with_feature()
        out = fileops.update_feature("app", "dark-mode", {"title": "Night mode"})
        self.assertIn("Night mode", (self.root / "projects/acme/products/app/roadmap.md").read_text())
        self.assertNotIn("id", out)  # sanity: no stale id key leaks through
        self.assertEqual(out["title"], "Night mode")

    def test_update_feature_unknown_raises(self):
        self._make_product_with_feature()
        with self.assertRaises(fileops.ActionError):
            fileops.update_feature("app", "nope", {"why": "x"})

    def test_delete_feature_removes_the_line(self):
        self._make_product_with_feature()
        fileops.delete_feature("app", "dark-mode")
        roadmap = (self.root / "projects/acme/products/app/roadmap.md").read_text()
        self.assertNotIn("Dark mode", roadmap)

    def test_delete_feature_unknown_raises(self):
        self._make_product_with_feature()
        with self.assertRaises(fileops.ActionError):
            fileops.delete_feature("app", "nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fileops_crud.py -k feature -v`
Expected: FAIL with `AttributeError: ... no attribute 'update_feature'`

- [ ] **Step 3: Implement the helper, parser, and both functions**

In `dashboard/fileops.py`, replace the body of `add_feature` (currently building `text` via inline marker logic) with a call to a new shared helper. First, insert this helper immediately **before** `def add_feature`:

```python
def _append_roadmap_line(text: str, section: str, line: str) -> str:
    """Append one checklist line under `## {section}`, creating the heading if needed."""
    marker = f"## {section}"
    if marker not in text:
        text = text.rstrip() + f"\n\n{marker}\n\n"
    if not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


_FEATURE_LINE_RE = re.compile(r"^(\s*- \[[ xX]\])\s*(.*)$")


def _parse_feature_line(line: str):
    """Return (checkbox_prefix, title, why, priority) or None if not a checklist line."""
    m = _FEATURE_LINE_RE.match(line)
    if not m:
        return None
    checkbox, rest = m.group(1), m.group(2)
    parts = [p.strip() for p in rest.split(" — ")]
    title = parts[0]
    why, priority = "", ""
    for part in parts[1:]:
        pm = re.match(r"^priority:\s*(.*)$", part, re.I)
        if pm:
            priority = pm.group(1).strip().lower()
        elif not why:
            why = part
    return checkbox, title, why, priority


def _find_feature_line_index(lines: list, feature_id: str):
    """Return (line_index, current_section) for the checklist line whose
    slug_key(title) matches feature_id, or None."""
    section = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        parsed = _parse_feature_line(line)
        if parsed and slug_key(parsed[1]) == feature_id:
            return i, section
    return None
```

Now replace `add_feature`'s body. Find this block (the tail of the existing function, from `marker = f"## {section}"` through `text += line + "\n"`):

```python
    marker = f"## {section}"
    if marker not in text:
        text = text.rstrip() + f"\n\n{marker}\n\n"
    if not text.endswith("\n"):
        text += "\n"
    why = (fields.get("why") or "").strip()
    line = f"- [ ] {title}"
    if why:
        line += f" — {why}"
    prio = (fields.get("priority") or "").strip().lower()
    if prio in FEATURE_PRIORITIES:
        line += f" — priority: {prio}"
    text += line + "\n"
    _write_project_doc(project_slug, "roadmap", text, path=roadmap)
```

Replace it with:

```python
    why = (fields.get("why") or "").strip()
    line = f"- [ ] {title}"
    if why:
        line += f" — {why}"
    prio = (fields.get("priority") or "").strip().lower()
    if prio in FEATURE_PRIORITIES:
        line += f" — priority: {prio}"
    text = _append_roadmap_line(text, section, line)
    _write_project_doc(project_slug, "roadmap", text, path=roadmap)
```

Then add `update_feature` and `delete_feature` immediately after `add_feature` (right before `def write_roadmap`):

```python
def update_feature(product_slug: str, feature_id: str, fields: dict) -> dict:
    feature_id = (feature_id or "").strip()
    if not feature_id:
        raise ActionError("feature id is required")
    prod_dir, project_slug = _product_dir(product_slug)
    roadmap = prod_dir / "roadmap.md"
    if not roadmap.exists():
        raise ActionError(f"feature '{feature_id}' not found")
    lines = roadmap.read_text(encoding="utf-8").splitlines()
    found = _find_feature_line_index(lines, feature_id)
    if not found:
        raise ActionError(f"feature '{feature_id}' not found")
    idx, cur_section = found
    checkbox, cur_title, cur_why, cur_priority = _parse_feature_line(lines[idx])
    title = (fields.get("title") or cur_title).strip()
    why = fields.get("why") if fields.get("why") is not None else cur_why
    priority = (fields.get("priority") if fields.get("priority") is not None else cur_priority) or ""
    priority = priority.strip().lower()
    new_line = f"{checkbox} {title}"
    if why:
        new_line += f" — {why}"
    if priority in FEATURE_PRIORITIES:
        new_line += f" — priority: {priority}"
    target_section = cur_section
    if fields.get("section"):
        target_section = _roadmap_section_name(fields["section"], project_slug)
    if target_section != cur_section:
        del lines[idx]
        text = "\n".join(lines)
        if not text.endswith("\n"):
            text += "\n"
        text = _append_roadmap_line(text, target_section, new_line)
    else:
        lines[idx] = new_line
        text = "\n".join(lines) + "\n"
    _write_project_doc(project_slug, "roadmap", text, path=roadmap)
    reindex()
    return {
        "id": _composed_id(lk_feature(product_slug, slug_key(title))),
        "title": title,
        "product": product_slug,
        "section": target_section,
    }


def delete_feature(product_slug: str, feature_id: str) -> dict:
    feature_id = (feature_id or "").strip()
    if not feature_id:
        raise ActionError("feature id is required")
    prod_dir, _project_slug = _product_dir(product_slug)
    roadmap = prod_dir / "roadmap.md"
    if not roadmap.exists():
        raise ActionError(f"feature '{feature_id}' not found")
    lines = roadmap.read_text(encoding="utf-8").splitlines()
    found = _find_feature_line_index(lines, feature_id)
    if not found:
        raise ActionError(f"feature '{feature_id}' not found")
    idx, _section = found
    del lines[idx]
    roadmap.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reindex()
    return {"id": feature_id, "product": product_slug, "deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fileops_crud.py -k feature -v`
Expected: 6 passed

Also re-run the existing `add-feature` regression test to confirm the refactor didn't break it:
Run: `python -m pytest tests/test_osctl.py -k add_feature -v`
Expected: passes (same as before the refactor)

- [ ] **Step 5: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_crud.py
git commit -m "feat: add fileops.update_feature/delete_feature; share roadmap-append helper with add_feature"
```

---

### Task 4: osctl — five new CLI subcommands

**Files:**
- Modify: `dashboard/osctl.py` (insert after `update-experiment` at line 178, and after `add-feature` at line 196)
- Test: `tests/test_osctl.py`

**Interfaces:**
- Consumes: `fileops.update_memo`, `fileops.delete_memo`, `fileops.delete_experiment`, `fileops.update_feature`, `fileops.delete_feature` (Tasks 1–3), `_fields` helper (existing, `dashboard/osctl.py:32`)
- Produces: `update-memo`, `delete-memo`, `delete-experiment`, `update-feature`, `delete-feature` subcommands, each printing one JSON line via the existing `main()`/`_emit` machinery

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_osctl.py`, inside `class T` (place near other memo/experiment/feature tests):

```python
    def test_update_memo_and_delete_memo(self):
        run(["create-project", "--slug", "acme", "--name", "Acme"])
        c, out = run(["create-memo", "--project", "acme", "--type", "assessment",
                      "--recommendation", "go"])
        self.assertEqual(c, 0)
        c, out = run(["update-memo", "--project", "acme", "--type", "assessment",
                      "--version", "1", "--recommendation", "wait"])
        self.assertEqual(c, 0)
        self.assertTrue(out["ok"])
        c, out = run(["delete-memo", "--project", "acme", "--type", "assessment", "--version", "1"])
        self.assertEqual(c, 0)
        self.assertTrue(out["deleted"])

    def test_delete_experiment(self):
        run(["create-project", "--slug", "acme", "--name", "Acme"])
        run(["create-experiment", "--project", "acme", "--assumption", "people will pay",
             "--stem", "will-pay"])
        c, out = run(["delete-experiment", "--project", "acme", "--stem", "will-pay"])
        self.assertEqual(c, 0)
        self.assertTrue(out["deleted"])

    def test_update_feature_and_delete_feature(self):
        run(["create-project", "--slug", "acme", "--name", "Acme"])
        run(["create-product", "--project", "acme", "--slug", "app", "--name", "Acme App"])
        run(["add-feature", "--product", "app", "--title", "Dark mode"])
        c, out = run(["update-feature", "--product", "app", "--id", "dark-mode",
                      "--priority", "high"])
        self.assertEqual(c, 0)
        self.assertTrue(out["ok"])
        c, out = run(["delete-feature", "--product", "app", "--id", "dark-mode"])
        self.assertEqual(c, 0)
        self.assertTrue(out["deleted"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_osctl.py -k "update_memo_and_delete_memo or delete_experiment or update_feature_and_delete_feature" -v`
Expected: FAIL with `argument --run/cmd: invalid choice` or similar (subcommands don't exist yet)

- [ ] **Step 3: Implement the five subcommands**

In `dashboard/osctl.py`, insert immediately after the `update-experiment` block (after the line `a.project, a.stem, _fields(a, ["assumption", "success_criteria", "kill_criteria"])))`, before `p = sub.add_parser("create-product", ...)`:

```python
    p = sub.add_parser("update-memo", help="Patch an existing memo JSON (same version, in place)")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, dest="memo_type")
    p.add_argument("--version", required=True, type=int)
    p.add_argument("--summary")
    p.add_argument("--recommendation")
    p.add_argument("--problem-statement", dest="problem_statement")
    p.add_argument("--body-json", dest="body_json", default="",
                   help="Extra memo fields as JSON (--body-json or stdin when --text empty)")
    def _update_memo(a):
        fields = _fields(a, ["summary", "recommendation", "problem_statement"])
        raw = (a.body_json or "").strip()
        if raw:
            fields.update(json.loads(raw))
        return fileops.update_memo(a.project, a.memo_type, a.version, fields)
    p.set_defaults(_run=_update_memo)

    p = sub.add_parser("delete-memo", help="Delete one memo version JSON")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, dest="memo_type")
    p.add_argument("--version", required=True, type=int)
    p.set_defaults(_run=lambda a: fileops.delete_memo(a.project, a.memo_type, a.version))

    p = sub.add_parser("delete-experiment", help="Delete strategy/experiments/<stem>.json")
    p.add_argument("--project", required=True)
    p.add_argument("--stem", required=True)
    p.set_defaults(_run=lambda a: fileops.delete_experiment(a.project, a.stem))
```

Then insert immediately after the `add-feature` block (after the line `a.product, _fields(a, ["title", "section", "why", "priority"])))`), before `p = sub.add_parser("update-roadmap", ...)`:

```python
    p = sub.add_parser("update-feature", help="Patch one roadmap checklist line")
    p.add_argument("--product", required=True)
    p.add_argument("--id", required=True, dest="feature_id")
    p.add_argument("--title")
    p.add_argument("--why")
    p.add_argument("--section")
    p.add_argument("--priority")
    p.set_defaults(_run=lambda a: fileops.update_feature(
        a.product, a.feature_id, _fields(a, ["title", "why", "section", "priority"])))

    p = sub.add_parser("delete-feature", help="Remove one roadmap checklist line")
    p.add_argument("--product", required=True)
    p.add_argument("--id", required=True, dest="feature_id")
    p.set_defaults(_run=lambda a: fileops.delete_feature(a.product, a.feature_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_osctl.py -k "update_memo_and_delete_memo or delete_experiment or update_feature_and_delete_feature" -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/osctl.py tests/test_osctl.py
git commit -m "feat: add update-memo/delete-memo/delete-experiment/update-feature/delete-feature osctl commands"
```

---

### Task 5: server.py — six new HTTP routes

**Files:**
- Modify: `dashboard/server.py` (insert into `do_POST`, near the existing `/memo/new`, `/experiment/new`, `/feature/new` branches around line 838–850)
- Test: `tests/test_server_briefs_voices.py` is the *pattern* reference; new tests go in a new file `tests/test_server_crud_parity.py` (memo/experiment/feature routes don't belong in the briefs/voices file, which is profile-scoped, not project/product-scoped)

**Interfaces:**
- Consumes: `fileops.update_memo`, `fileops.delete_memo`, `fileops.delete_experiment`, `fileops.update_feature`, `fileops.delete_feature` (Tasks 1–3), `fileops.update_experiment` (existing)
- Produces: `POST /api/project/<slug>/memo/<type>/<version>/update`, `POST /api/project/<slug>/memo/<type>/<version>/delete`, `POST /api/project/<slug>/experiment/<stem>/update`, `POST /api/project/<slug>/experiment/<stem>/delete`, `POST /api/product/<slug>/feature/<id>/update`, `POST /api/product/<slug>/feature/<id>/delete` — every response is `{"ok": True, **result}` on update, `{"ok": True, **result}` on delete too (matches the milestone-delete convention at `server.py:871`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server_crud_parity.py`:

```python
import io, json, tempfile, unittest
from pathlib import Path

import index
from tests.test_index_projects import write
import dashboard.server as server

# server.py's bare `import fileops`/`import db` cache under different
# sys.modules keys than `dashboard.fileops`/`dashboard.db` — routes use
# server's own references, so tests must patch those. Same caveat as
# tests/test_server_briefs_voices.py.
fileops = server.fileops
db = server.db


def _handler():
    h = server.Handler.__new__(server.Handler)
    h.send_response = h.send_header = h.end_headers = lambda *a, **k: None
    return h


def _get(path):
    h = _handler()
    h.path = path
    h.wfile = io.BytesIO()
    h.do_GET()
    return json.loads(h.wfile.getvalue().decode())


def _post(path, body):
    h = _handler()
    payload = json.dumps(body).encode()
    h.path = path
    h.headers = {"Content-Length": str(len(payload))}
    h.rfile = io.BytesIO(payload)
    h.wfile = io.BytesIO()
    h.do_POST()
    return json.loads(h.wfile.getvalue().decode())


class CrudParityRoutesTest(unittest.TestCase):
    def setUp(self):
        self._prev_root = fileops.ROOT
        self._prev_db_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        fileops.ROOT = self._prev_root
        db.DB_PATH = self._prev_db_path
        self.tmp.cleanup()

    def test_memo_update_and_delete_routes(self):
        created = _post("/api/project/acme/memo/new", {"type": "assessment", "recommendation": "go"})
        self.assertTrue(created["ok"])
        upd = _post("/api/project/acme/memo/assessment/1/update", {"recommendation": "wait"})
        self.assertTrue(upd["ok"])
        proj = _get("/api/project/acme")
        memo = next(m for m in proj["memos"] if m["type"] == "assessment" and m["version"] == 1)
        self.assertEqual(memo["body"]["recommendation"], "wait")
        deleted = _post("/api/project/acme/memo/assessment/1/delete", {})
        self.assertTrue(deleted["ok"])
        self.assertTrue(deleted["deleted"])

    def test_experiment_update_and_delete_routes(self):
        created = _post("/api/project/acme/experiment/new",
                         {"assumption": "people will pay", "stem": "will-pay"})
        self.assertTrue(created["ok"])
        upd = _post("/api/project/acme/experiment/will-pay/update", {"success_criteria": "10 signups"})
        self.assertTrue(upd["ok"])
        proj = _get("/api/project/acme")
        exp = next(x for x in proj["experiments"] if x["stem"] == "will-pay")
        self.assertEqual(exp["body"]["success_criteria"], "10 signups")
        deleted = _post("/api/project/acme/experiment/will-pay/delete", {})
        self.assertTrue(deleted["ok"])
        self.assertTrue(deleted["deleted"])

    def test_feature_update_and_delete_routes(self):
        _post("/api/project/acme/product/new", {"slug": "app", "name": "Acme App"})
        created = _post("/api/product/app/feature/new", {"title": "Dark mode"})
        self.assertTrue(created["ok"])
        upd = _post("/api/product/app/feature/dark-mode/update", {"priority": "high"})
        self.assertTrue(upd["ok"])
        deleted = _post("/api/product/app/feature/dark-mode/delete", {})
        self.assertTrue(deleted["ok"])
        self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server_crud_parity.py -v`
Expected: FAIL with `{"error": "unknown endpoint"}` assertion errors (routes don't exist yet)

- [ ] **Step 3: Implement the six routes**

In `dashboard/server.py`, insert immediately after the existing `/experiment/new` branch and before the existing `/product/new` branch (i.e. right after `return self._send(200, {"ok": True, **fileops.create_experiment(proj, body)})`):

```python
            if path.startswith("/api/project/") and "/memo/" in path and path.endswith("/update"):
                rest = path[len("/api/project/"):-len("/update")]
                proj, tail = rest.split("/memo/", 1)
                mtype, version = tail.rstrip("/").split("/")
                return self._send(200, {"ok": True, **fileops.update_memo(proj, mtype, int(version), body)})
            if path.startswith("/api/project/") and "/memo/" in path and path.endswith("/delete"):
                rest = path[len("/api/project/"):-len("/delete")]
                proj, tail = rest.split("/memo/", 1)
                mtype, version = tail.rstrip("/").split("/")
                return self._send(200, {"ok": True, **fileops.delete_memo(proj, mtype, int(version))})
            if path.startswith("/api/project/") and "/experiment/" in path and path.endswith("/update"):
                rest = path[len("/api/project/"):-len("/update")]
                proj, tail = rest.split("/experiment/", 1)
                stem = tail.rstrip("/")
                return self._send(200, {"ok": True, **fileops.update_experiment(proj, stem, body)})
            if path.startswith("/api/project/") and "/experiment/" in path and path.endswith("/delete"):
                rest = path[len("/api/project/"):-len("/delete")]
                proj, tail = rest.split("/experiment/", 1)
                stem = tail.rstrip("/")
                return self._send(200, {"ok": True, **fileops.delete_experiment(proj, stem)})
```

Then insert immediately after the existing `/feature/new` branch and before the `/profile/new` branch (i.e. right after `return self._send(200, {"ok": True, **fileops.add_feature(prod_slug, body)})`):

```python
            if path.startswith("/api/product/") and "/feature/" in path and path.endswith("/update"):
                rest = path[len("/api/product/"):-len("/update")]
                prod_slug, tail = rest.split("/feature/", 1)
                fid = tail.rstrip("/")
                return self._send(200, {"ok": True, **fileops.update_feature(prod_slug, fid, body)})
            if path.startswith("/api/product/") and "/feature/" in path and path.endswith("/delete"):
                rest = path[len("/api/product/"):-len("/delete")]
                prod_slug, tail = rest.split("/feature/", 1)
                fid = tail.rstrip("/")
                return self._send(200, {"ok": True, **fileops.delete_feature(prod_slug, fid)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_server_crud_parity.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/server.py tests/test_server_crud_parity.py
git commit -m "feat: add HTTP routes for memo/experiment/feature update+delete"
```

---

### Task 6: app.js — form-field prefill support + memo card edit/delete UI

This is the first UI task, so it also lands the one shared JS change every other UI task depends on: making `renderSchemaField` prefillable. (`renderMdSubsections`'s `titles` override, needed only by Task 9, is *not* added here — it stays local to that task.)

**Files:**
- Modify: `dashboard/app.js`:
  - `renderSchemaField` (line 335) — add optional `values` param
  - `renderMemoCard` call sites in `renderOverviewSection` (~line 792), `renderValidationSection` (~line 809), `renderPricingSection` (~line 860) — pass edit/delete actions
  - Add `memoCardActions`, `renderEditMemo`, `renderConfirmDeleteMemo`, `wireMemoCardButtons`
  - Add 2 routes to the `ROUTES` table (~line 197)
  - `renderProjectSection` tail (~line 992) — call `wireMemoCardButtons`

**Interfaces:**
- Consumes: `POST /api/project/<slug>/memo/<type>/<version>/update`, `/delete` (Task 5), `schemaFields`, `jpost`, `api`, `confirmPage`, `renderSecGroup`, `memoArtifactId`, `memoTypeLabel`, `pageHeader`, `formVals`, `toast`, `renderRail`, `navigate` (all existing)
- Produces: `renderSchemaField(spec, values={})` — new optional second param, backward compatible (existing callers pass nothing, get `""` exactly as before). `memoCardActions(slug, memo)` returning button HTML or `""`. Later tasks (7, 8) copy this exact pattern for experiments/features.

- [ ] **Step 1: Manual verification harness (no JS test runner in this repo)**

This repo has no JS test framework (confirmed: no `package.json` test script, no `*.test.js` files). Per project convention, UI changes are verified by running the dashboard and exercising the flow in-browser — do that at the end of Step 4, not as an automated step.

- [ ] **Step 2: Make `renderSchemaField` prefillable**

In `dashboard/app.js`, replace:

```javascript
function renderSchemaField(spec){
  const key = spec.key;
  const label = spec.label || humanizeKey(key);
  const req = spec.required ? " required" : "";
  const ph = spec.placeholder ? ` placeholder="${esc(spec.placeholder)}"` : "";
  if (spec.type === "textarea" || spec.type === "evidence") {
    const hint = spec.type === "evidence" ? ' placeholder="One signal per line"' : ph;
    return `${flabel(label)}${fta(key, "", spec.rows || 3, hint + req)}`;
  }
  if (spec.type === "select") {
    const opts = (spec.options || []).map(o => [o, o === "" ? "—" : (o.charAt(0).toUpperCase() + o.slice(1))]);
    return `${flabel(label)}${fsel(key, opts, spec.default || opts[0]?.[0] || "")}`;
  }
  return `${flabel(label)}${finput(key, "", ph + req)}`;
}
```

with:

```javascript
function renderSchemaField(spec, values={}){
  const key = spec.key;
  const label = spec.label || humanizeKey(key);
  const req = spec.required ? " required" : "";
  const ph = spec.placeholder ? ` placeholder="${esc(spec.placeholder)}"` : "";
  const val = values[key];
  if (spec.type === "textarea" || spec.type === "evidence") {
    const hint = spec.type === "evidence" ? ' placeholder="One signal per line"' : ph;
    return `${flabel(label)}${fta(key, val ?? "", spec.rows || 3, hint + req)}`;
  }
  if (spec.type === "select") {
    const opts = (spec.options || []).map(o => [o, o === "" ? "—" : (o.charAt(0).toUpperCase() + o.slice(1))]);
    return `${flabel(label)}${fsel(key, opts, val ?? (spec.default || opts[0]?.[0] || ""))}`;
  }
  return `${flabel(label)}${finput(key, val ?? "", ph + req)}`;
}
```

- [ ] **Step 3: Add `memoCardActions`, edit/delete render functions, and wiring**

Add after `memoArtifactId` (line 723–724, right after `function memoArtifactId(projectSlug, memo){ return composedIdOnly(memo.id, OSID.memo(projectSlug, memo.type, memo.version)); }`):

```javascript
function memoCardActions(slug, memo){
  if (!memo) return "";
  return `<button type="button" class="btn" data-edit-memo="${esc(slug)}" data-memo-type="${esc(memo.type)}" data-memo-version="${esc(memo.version)}" style="padding:4px 10px;font-size:11px">✎ Edit</button>` +
         `<button type="button" class="btn danger-btn" data-del-memo="${esc(slug)}" data-memo-type="${esc(memo.type)}" data-memo-version="${esc(memo.version)}" style="padding:4px 10px;font-size:11px">🗑</button>`;
}

function wireMemoCardButtons(){
  $("#main").querySelectorAll("[data-edit-memo]").forEach(btn => {
    btn.onclick = () => navigate(`#/project/${btn.dataset.editMemo}/memo/${btn.dataset.memoType}/${btn.dataset.memoVersion}/edit`);
  });
  $("#main").querySelectorAll("[data-del-memo]").forEach(btn => {
    btn.onclick = () => navigate(`#/project/${btn.dataset.delMemo}/memo/${btn.dataset.memoType}/${btn.dataset.memoVersion}/delete`);
  });
}

function memoBackSection(memoType){
  return memoType === "problem-validation" ? "validation" : memoType === "assessment" ? "overview" : "pricing";
}

async function renderEditMemo(projectSlug, memoType, version){
  await ensureSchemas();
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const label = memoTypeLabel(memoType);
  const p = await api(`/api/project/${projectSlug}`);
  const memo = (p.memos || []).find(m => m.type === memoType && String(m.version) === String(version));
  if (!memo) { $("#main").innerHTML = `<div class="scroll"><p class="memo-empty">Memo not found.</p></div>`; return; }
  const fields = schemaFields("memo", memoType);
  const values = memo.body || {};
  const formHtml = fields.map(f => renderSchemaField(f, values)).join("");
  $("#main").innerHTML = `${pageHeader(`Edit · ${label}`, projName, `<button class="btn primary" id="em2-save">Save</button>`, memoArtifactId(projectSlug, memo))}
    <div class="scroll"><div class="fpage">${formHtml}</div></div>`;
  document.getElementById("em2-save").onclick = async () => {
    try {
      await jpost(`/api/project/${projectSlug}/memo/${memoType}/${version}/update`, formVals($("#main")));
      toast("Saved ✓");
      await renderRail(); navigate(`#/project/${projectSlug}/${memoBackSection(memoType)}`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderConfirmDeleteMemo(projectSlug, memoType, version){
  const label = memoTypeLabel(memoType);
  confirmPage(`Delete ${label}`, `Delete this ${label.toLowerCase()} memo (v${version})? This cannot be undone.`, async () => {
    try {
      await jpost(`/api/project/${projectSlug}/memo/${memoType}/${version}/delete`, {});
      toast("Deleted ✓");
      await renderRail(); navigate(`#/project/${projectSlug}/${memoBackSection(memoType)}`);
    } catch (e) { toast("✗ " + e.message); }
  });
}
```

- [ ] **Step 4: Wire the routes, the three call sites, and the section-tail invocation**

In the `ROUTES` table, immediately after `[/^\/project\/([^/]+)\/memo\/new\/([^/]+)$/,   ([s,t])  => renderNewMemo(s,t)],`, add:

```javascript
  [/^\/project\/([^/]+)\/memo\/([^/]+)\/(\d+)\/edit$/,   ([s,t,v]) => renderEditMemo(s,t,v)],
  [/^\/project\/([^/]+)\/memo\/([^/]+)\/(\d+)\/delete$/, ([s,t,v]) => renderConfirmDeleteMemo(s,t,v)],
```

In `renderOverviewSection`, change:
```javascript
  html += renderSecGroup("GTM assessment",
    (as && ab.riskiest_assumption) ? renderMemoCard(slug, as, { title: "GTM assessment", headless: true })
      : `<div class="sec-missing">No assessment memo · <span class="sec-hint"><code>/gtm-assessment</code></span></div>`,
    (as && ab.riskiest_assumption) ? memoArtifactId(slug, as) : null);
```
to:
```javascript
  html += renderSecGroup("GTM assessment",
    (as && ab.riskiest_assumption) ? renderMemoCard(slug, as, { title: "GTM assessment", headless: true })
      : `<div class="sec-missing">No assessment memo · <span class="sec-hint"><code>/gtm-assessment</code></span></div>`,
    (as && ab.riskiest_assumption) ? memoArtifactId(slug, as) : null,
    (as && ab.riskiest_assumption) ? memoCardActions(slug, as) : "");
```

In `renderValidationSection`, change:
```javascript
  html += renderSecGroup("Problem validation",
    pv ? renderMemoCard(slug, pv, { headless: true }) : `<div class="sec-missing">No memo yet · <span class="sec-hint"><code>/problem-validation</code></span></div>`,
    pv ? memoArtifactId(slug, pv) : null);
```
to:
```javascript
  html += renderSecGroup("Problem validation",
    pv ? renderMemoCard(slug, pv, { headless: true }) : `<div class="sec-missing">No memo yet · <span class="sec-hint"><code>/problem-validation</code></span></div>`,
    pv ? memoArtifactId(slug, pv) : null,
    pv ? memoCardActions(slug, pv) : "");
```

In `renderPricingSection`, change:
```javascript
    html += renderSecGroup(label, inner, m ? memoArtifactId(slug, m) : null);
```
to:
```javascript
    html += renderSecGroup(label, inner, m ? memoArtifactId(slug, m) : null, m ? memoCardActions(slug, m) : "");
```

Finally, in `renderProjectSection`, find the existing lines:
```javascript
  if (section === "product") wireProductFeatureButtons(slug);
  if (section === "technical") wireDocSubsectionEditButtons(slug);
```
and change to:
```javascript
  if (section === "product") wireProductFeatureButtons(slug);
  if (section === "technical") wireDocSubsectionEditButtons(slug);
  if (["overview", "validation", "pricing"].includes(section)) wireMemoCardButtons();
```

- [ ] **Step 5: Manual verification**

Start the dashboard (`python3 dashboard/server.py`), open a project with at least one GTM assessment memo (or create one via the "+ Memo" button), and confirm:
1. Overview tab shows ✎/🗑 next to the GTM assessment card's id chip.
2. ✎ opens a form prefilled with the memo's current field values; changing a field and saving updates the card and returns you to the tab.
3. 🗑 shows a confirm page; confirming removes the memo and returns you to the tab.
4. Repeat on the Validation tab (problem-validation memo) and Pricing tab (any memo type present).

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: add edit/delete buttons to memo cards (Overview/Validation/Pricing tabs)"
```

---

### Task 7: app.js — experiment card edit/delete UI

**Files:**
- Modify: `dashboard/app.js`:
  - `renderExperimentCard` (line 820) — pass actions as `renderArtifactHead`'s trailing arg
  - Add `experimentCardActions`, `renderEditExperiment`, `renderConfirmDeleteExperiment`, `wireExperimentCardButtons`
  - Add 2 routes to `ROUTES`
  - `renderProjectSection` tail — call `wireExperimentCardButtons`

**Interfaces:**
- Consumes: `POST /api/project/<slug>/experiment/<stem>/update`, `/delete` (Task 5), `renderSchemaField(spec, values)` (Task 6), `schemaFields`, `confirmPage`, `composedIdOnly`, `OSID.experiment`
- Produces: `experimentCardActions(slug, stem)` — same shape as `memoCardActions`

- [ ] **Step 1: Update `renderExperimentCard` and add `experimentCardActions`**

Replace:
```javascript
function renderExperimentCard(slug, x){
  const stem = x.stem || (x.file_path || "").split("/").pop().replace(/\.json$/, "") || x.id;
  const id = composedIdOnly(x.id, OSID.experiment(slug, stem));
  const b = x.body || {};
  let body = `<div><b>Status</b> · ${esc(x.status || "?")}`;
  if (x.decision) body += ` · decision <b>${esc(x.decision)}</b>`;
  if (x.duration_days) body += ` · ${esc(x.duration_days)}d`;
  if (x.started_on) body += ` · started ${esc(x.started_on)}`;
  body += `</div>`;
  if (x.result) body += `<div><b>Result</b> · ${esc(x.result)}</div>`;
  if (b.success_criteria) body += `<div><b>Success</b> · ${esc(b.success_criteria)}</div>`;
  if (b.kill_criteria) body += `<div><b>Kill</b> · ${esc(b.kill_criteria)}</div>`;
  return `<div class="pcard">${renderArtifactHead(x.assumption || stem, id)}<div class="sec-body">${body}</div></div>`;
}
```
with:
```javascript
function renderExperimentCard(slug, x){
  const stem = x.stem || (x.file_path || "").split("/").pop().replace(/\.json$/, "") || x.id;
  const id = composedIdOnly(x.id, OSID.experiment(slug, stem));
  const b = x.body || {};
  let body = `<div><b>Status</b> · ${esc(x.status || "?")}`;
  if (x.decision) body += ` · decision <b>${esc(x.decision)}</b>`;
  if (x.duration_days) body += ` · ${esc(x.duration_days)}d`;
  if (x.started_on) body += ` · started ${esc(x.started_on)}`;
  body += `</div>`;
  if (x.result) body += `<div><b>Result</b> · ${esc(x.result)}</div>`;
  if (b.success_criteria) body += `<div><b>Success</b> · ${esc(b.success_criteria)}</div>`;
  if (b.kill_criteria) body += `<div><b>Kill</b> · ${esc(b.kill_criteria)}</div>`;
  return `<div class="pcard">${renderArtifactHead(x.assumption || stem, id, experimentCardActions(slug, stem))}<div class="sec-body">${body}</div></div>`;
}

function experimentCardActions(slug, stem){
  return `<button type="button" class="btn" data-edit-exp="${esc(slug)}" data-exp-stem="${esc(stem)}" style="padding:4px 10px;font-size:11px">✎ Edit</button>` +
         `<button type="button" class="btn danger-btn" data-del-exp="${esc(slug)}" data-exp-stem="${esc(stem)}" style="padding:4px 10px;font-size:11px">🗑</button>`;
}
```

- [ ] **Step 2: Add `renderEditExperiment`, `renderConfirmDeleteExperiment`, `wireExperimentCardButtons`**

Add after `renderNewExperiment` (right after its closing `}`, before `function renderNewProduct`):

```javascript
function wireExperimentCardButtons(){
  $("#main").querySelectorAll("[data-edit-exp]").forEach(btn => {
    btn.onclick = () => navigate(`#/project/${btn.dataset.editExp}/experiment/${btn.dataset.expStem}/edit`);
  });
  $("#main").querySelectorAll("[data-del-exp]").forEach(btn => {
    btn.onclick = () => navigate(`#/project/${btn.dataset.delExp}/experiment/${btn.dataset.expStem}/delete`);
  });
}

async function renderEditExperiment(projectSlug, stem){
  await ensureSchemas();
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const p = await api(`/api/project/${projectSlug}`);
  const exp = (p.experiments || []).find(x => (x.stem || "") === stem);
  if (!exp) { $("#main").innerHTML = `<div class="scroll"><p class="memo-empty">Experiment not found.</p></div>`; return; }
  const values = exp.body || {};
  const formHtml = schemaFields("experiment").map(f => renderSchemaField(f, values)).join("");
  $("#main").innerHTML = `${pageHeader("Edit experiment", projName, `<button class="btn primary" id="ee-save">Save</button>`, composedIdOnly(exp.id, OSID.experiment(projectSlug, stem)))}
    <div class="scroll"><div class="fpage">${formHtml}</div></div>`;
  document.getElementById("ee-save").onclick = async () => {
    const data = formVals($("#main"));
    if (!data.assumption?.trim()) return toast("Assumption is required");
    try {
      await jpost(`/api/project/${projectSlug}/experiment/${stem}/update`, data);
      toast("Saved ✓");
      await renderRail(); navigate(`#/project/${projectSlug}/experiments`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderConfirmDeleteExperiment(projectSlug, stem){
  confirmPage("Delete experiment", "Delete this experiment? This cannot be undone.", async () => {
    try {
      await jpost(`/api/project/${projectSlug}/experiment/${stem}/delete`, {});
      toast("Deleted ✓");
      await renderRail(); navigate(`#/project/${projectSlug}/experiments`);
    } catch (e) { toast("✗ " + e.message); }
  });
}
```

- [ ] **Step 3: Wire routes and section-tail invocation**

In `ROUTES`, immediately after `[/^\/project\/([^/]+)\/experiment\/new$/,     ([s])    => renderNewExperiment(s)],`, add:

```javascript
  [/^\/project\/([^/]+)\/experiment\/([^/]+)\/edit$/,   ([s,stem]) => renderEditExperiment(s,stem)],
  [/^\/project\/([^/]+)\/experiment\/([^/]+)\/delete$/, ([s,stem]) => renderConfirmDeleteExperiment(s,stem)],
```

In `renderProjectSection`, extend the same tail block from Task 6:
```javascript
  if (section === "experiments") wireExperimentCardButtons();
```

- [ ] **Step 4: Manual verification**

On the Experiments tab, confirm each experiment card shows ✎/🗑 next to its id chip, edit opens a prefilled 3-field form (assumption/success/kill criteria) that saves and returns to the tab, and delete confirms then removes the card.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: add edit/delete buttons to experiment cards"
```

---

### Task 8: app.js — roadmap feature edit/delete UI

**Files:**
- Modify: `dashboard/app.js`:
  - `renderFeatureCard` (line 865) — pass actions as `renderArtifactHead`'s trailing arg
  - Add `featureCardActions`, `renderEditFeature`, `renderConfirmDeleteFeature`, `wireFeatureCardButtons`
  - Add 2 routes to `ROUTES`
  - `renderProjectSection` tail — call `wireFeatureCardButtons`

**Interfaces:**
- Consumes: `POST /api/product/<slug>/feature/<id>/update`, `/delete` (Task 5), `renderSchemaField(spec, values)` (Task 6), `schemaFields`, `confirmPage`, `OSID.feat`, `OSID.slugKey`

- [ ] **Step 1: Update `renderFeatureCard` and add `featureCardActions`**

Replace:
```javascript
function renderFeatureCard(prod, f){
  const fid = composedIdOnly(f.id, OSID.feat(prod.slug, OSID.slugKey(f.title)));
  const badges = `<div class="artifact-badges">${featureStatusPill(f.status)}${
    f.priority ? `<span class="prio-tag">${esc(f.priority)}</span>` : ""}${
    f.target_date ? `<span class="prio-tag">${esc(f.target_date)}</span>` : ""}</div>`;
  const body = f.why
    ? `<div class="sec-body">${esc(f.why)}</div>`
    : `<div class="sec-body memo-empty">No description — add after title in roadmap: <code>Title — one-line why</code></div>`;
  return `<div class="pcard">${renderArtifactHead(f.title, fid)}${badges}${body}</div>`;
}
```
with:
```javascript
function renderFeatureCard(prod, f){
  const fid = composedIdOnly(f.id, OSID.feat(prod.slug, OSID.slugKey(f.title)));
  const badges = `<div class="artifact-badges">${featureStatusPill(f.status)}${
    f.priority ? `<span class="prio-tag">${esc(f.priority)}</span>` : ""}${
    f.target_date ? `<span class="prio-tag">${esc(f.target_date)}</span>` : ""}</div>`;
  const body = f.why
    ? `<div class="sec-body">${esc(f.why)}</div>`
    : `<div class="sec-body memo-empty">No description — add after title in roadmap: <code>Title — one-line why</code></div>`;
  return `<div class="pcard">${renderArtifactHead(f.title, fid, featureCardActions(prod.slug, f))}${badges}${body}</div>`;
}

function featureCardActions(productSlug, feature){
  const fid = OSID.slugKey(feature.title);
  return `<button type="button" class="btn" data-edit-feat="${esc(productSlug)}" data-feat-id="${esc(fid)}" style="padding:4px 10px;font-size:11px">✎ Edit</button>` +
         `<button type="button" class="btn danger-btn" data-del-feat="${esc(productSlug)}" data-feat-id="${esc(fid)}" style="padding:4px 10px;font-size:11px">🗑</button>`;
}
```

- [ ] **Step 2: Add `renderEditFeature`, `renderConfirmDeleteFeature`, `wireFeatureCardButtons`**

Add after `renderNewFeature` (right after its closing `}`, before `// ── New profile ──` comment):

```javascript
function wireFeatureCardButtons(){
  $("#main").querySelectorAll("[data-edit-feat]").forEach(btn => {
    btn.onclick = () => navigate(`#/product/${btn.dataset.editFeat}/feature/${btn.dataset.featId}/edit`, { projectSlug: _NAV_EXTRAS.projectSlug });
  });
  $("#main").querySelectorAll("[data-del-feat]").forEach(btn => {
    btn.onclick = () => navigate(`#/product/${btn.dataset.delFeat}/feature/${btn.dataset.featId}/delete`, { projectSlug: _NAV_EXTRAS.projectSlug });
  });
}

async function renderEditFeature(productSlug, featureId, projectSlug){
  await ensureSchemas();
  const back = projectSlug ? `#/project/${projectSlug}/product` : "#/calendar";
  let fields = schemaFields("feature");
  let p = null;
  if (projectSlug) {
    try { p = await api(`/api/project/${projectSlug}`); if (p.feature?.length) fields = p.feature; } catch (_) { /* global schema defaults */ }
  }
  const feat = (p?.features || []).find(f => OSID.slugKey(f.title) === featureId && f.product_slug === productSlug);
  if (!feat) { $("#main").innerHTML = `<div class="scroll"><p class="memo-empty">Feature not found.</p></div>`; return; }
  const values = { title: feat.title, why: feat.why || "", section: feat.roadmap_section || "", priority: feat.priority || "" };
  const formHtml = fields.map(f => renderSchemaField(f, values)).join("");
  $("#main").innerHTML = `${pageHeader("Edit feature", productSlug, `<button class="btn primary" id="ef-save">Save</button>`, composedIdOnly(feat.id, OSID.feat(productSlug, featureId)))}
    <div class="scroll"><div class="fpage">${formHtml}</div></div>`;
  document.getElementById("ef-save").onclick = async () => {
    const data = formVals($("#main"));
    if (!data.title?.trim()) return toast("Title is required");
    try {
      await jpost(`/api/product/${productSlug}/feature/${featureId}/update`, data);
      toast("Saved ✓");
      await renderRail(); navigate(back);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderConfirmDeleteFeature(productSlug, featureId, projectSlug){
  const back = projectSlug ? `#/project/${projectSlug}/product` : "#/calendar";
  confirmPage("Delete feature", "Delete this feature from the roadmap? This cannot be undone.", async () => {
    try {
      await jpost(`/api/product/${productSlug}/feature/${featureId}/delete`, {});
      toast("Deleted ✓");
      await renderRail(); navigate(back);
    } catch (e) { toast("✗ " + e.message); }
  });
}
```

- [ ] **Step 3: Wire routes and section-tail invocation**

In `ROUTES`, immediately after `[/^\/product\/([^/]+)\/feature\/new$/,         ([ps])   => renderNewFeature(ps, _NAV_EXTRAS.projectSlug)],`, add:

```javascript
  [/^\/product\/([^/]+)\/feature\/([^/]+)\/edit$/,   ([ps,fid]) => renderEditFeature(ps,fid,_NAV_EXTRAS.projectSlug)],
  [/^\/product\/([^/]+)\/feature\/([^/]+)\/delete$/, ([ps,fid]) => renderConfirmDeleteFeature(ps,fid,_NAV_EXTRAS.projectSlug)],
```

In `renderProjectSection`, extend the tail block:
```javascript
  if (section === "product") wireProductFeatureButtons(slug);
  if (section === "product") wireFeatureCardButtons();
```

- [ ] **Step 4: Manual verification**

On the Product tab, confirm each feature card shows ✎/🗑, edit opens a prefilled form (title/why/section/priority) that saves and returns to the tab (including a section-move test), and delete confirms then removes the line from the roadmap.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: add edit/delete buttons to roadmap feature cards"
```

---

### Task 9: app.js — Validation tab intake subsections become editable

Closes the last named gap from the original ask: intake subsections on the Validation tab currently render as one read-only file card (via `renderFileCard` + `filterIntakeSections`), unlike the Technical tab's per-subsection editable cards. This wires Validation to the same `renderMdSubsections` mechanism Technical already uses, while preserving the existing curated subset (`validationTabSubsections`) instead of showing full intake.

**Files:**
- Modify: `dashboard/app.js`:
  - `renderMdSubsections` (line 688) — accept an optional `opts.titles` override
  - `renderValidationSection` (line 798) — swap intake rendering to `renderMdSubsections`
  - Delete now-dead `renderFileCard` (line 766) and `filterIntakeSections` (line 714)
  - `renderProjectSection` tail — also fire `wireDocSubsectionEditButtons` for the `validation` section

**Interfaces:**
- Consumes: `validationTabSubsections(p)` (existing), `renderMdSubsections`, `wireDocSubsectionEditButtons` (existing, already generic over `docKey`, already handles `docKey === "intake"`)

- [ ] **Step 1: Add the `titles` override to `renderMdSubsections`**

Replace:
```javascript
function renderMdSubsections(projectSlug, p, docKey, text, opts = {}){
  const order = projectDocSubsections(p, docKey);
```
with:
```javascript
function renderMdSubsections(projectSlug, p, docKey, text, opts = {}){
  const order = opts.titles || projectDocSubsections(p, docKey);
```

- [ ] **Step 2: Swap `renderValidationSection`'s intake rendering**

Replace:
```javascript
function renderValidationSection(slug, p, sec){
  const intake = (sec.artifacts || []).find(a => a.kind === "file" && (a.path || "").endsWith("strategy/intake.md"));
  const pv = latestMemo(p, "problem-validation");
  let html = "";
  const intakeFiltered = intake ? filterIntakeSections(intake.text, validationTabSubsections(p)) : "";
  html += renderSecGroup("Venture intake",
    intakeFiltered
      ? renderFileCard({ ...intake, text: intakeFiltered }, slug, { headless: true })
      : `<div class="sec-missing">No validation intake yet · <span class="sec-hint"><code>/venture-intake</code></span></div>`,
    docArtifactId(slug, intake));
  html += renderSecGroup("Problem validation",
    pv ? renderMemoCard(slug, pv, { headless: true }) : `<div class="sec-missing">No memo yet · <span class="sec-hint"><code>/problem-validation</code></span></div>`,
    pv ? memoArtifactId(slug, pv) : null,
    pv ? memoCardActions(slug, pv) : "");
  return html;
}
```
with:
```javascript
function renderValidationSection(slug, p, sec){
  const intake = (sec.artifacts || []).find(a => a.kind === "file" && (a.path || "").endsWith("strategy/intake.md"));
  const pv = latestMemo(p, "problem-validation");
  let html = "";
  html += intake
    ? `<div class="sec-subsections">${renderMdSubsections(slug, p, "intake", intake.text, { editable: true, titles: validationTabSubsections(p) })}</div>`
    : renderSecGroup("Venture intake", `<div class="sec-missing">No validation intake yet · <span class="sec-hint"><code>/venture-intake</code></span></div>`, docArtifactId(slug, intake));
  html += renderSecGroup("Problem validation",
    pv ? renderMemoCard(slug, pv, { headless: true }) : `<div class="sec-missing">No memo yet · <span class="sec-hint"><code>/problem-validation</code></span></div>`,
    pv ? memoArtifactId(slug, pv) : null,
    pv ? memoCardActions(slug, pv) : "");
  return html;
}
```

(Note: this assumes Task 6 already landed — `renderValidationSection` already has the `memoCardActions` call for `pv` from that task. If executing this task before Task 6 for any reason, keep the pre-Task-6 3-arg `renderSecGroup` call for "Problem validation" instead.)

- [ ] **Step 3: Delete the now-dead `renderFileCard` and `filterIntakeSections`**

Confirm no other references first:
Run: `grep -n "renderFileCard\|filterIntakeSections" dashboard/app.js`
Expected: only their own definitions remain (no call sites) after Step 2's edit — delete both function definitions entirely.

Delete:
```javascript
function fileCardTitle(artifact){
  const p=artifact.path||"";
  if(p.endsWith("intake.md")) return "Venture intake";
  if(p.endsWith("technical.md")) return "Technical";
  if(p.endsWith("project.md")) return "Project";
  return (artifact.label||"").split("/").pop()||"File";
}

function renderFileCard(artifact, projectSlug, opts = {}){
  const title = fileCardTitle(artifact);
  let raw = artifact.text;
  if (opts.headless && raw != null) raw = stripLeadingDocTitle(raw);
  const mdOpts = opts.headless ? { dropH1: true } : {};
  const content = raw != null ? formatMdDoc(raw, mdOpts) : `<p class="memo-empty">Could not load file.</p>`;
  const id = docArtifactId(projectSlug, artifact);
  if (opts.headless) {
    return `<div class="pcard"><div class="sec-body memo-body">${content}</div></div>`;
  }
  return `<div class="pcard">${renderArtifactHead(title, id)}<div class="sec-body memo-body">${content}</div></div>`;
}
```
and:
```javascript
function filterIntakeSections(text, allowedTitles){
  const allow = new Set(allowedTitles);
  return parseMdSections(text)
    .filter(s => allow.has(s.title) && s.body.trim())
    .map(s => `## ${s.title}\n\n${s.body.trim()}`)
    .join("\n\n");
}
```

Note: `fileCardTitle` is only used inside `renderFileCard` — confirm with the same grep before deleting it too.

- [ ] **Step 4: Wire `wireDocSubsectionEditButtons` for the validation section**

In `renderProjectSection`, change:
```javascript
  if (section === "technical") wireDocSubsectionEditButtons(slug);
```
to:
```javascript
  if (section === "technical" || section === "validation") wireDocSubsectionEditButtons(slug);
```

- [ ] **Step 5: Manual verification**

On the Validation tab, confirm the intake subsections (Stage & evidence, Market, Resources, Goals, Evidence log, or whatever the project's `validation_tab` config lists) each render as separate cards with a ✎ Edit button, matching the Technical tab's look. Confirm editing one subsection saves only that subsection and doesn't touch the others. Confirm "What it is" (or any subsection *not* in `validation_tab`) still does **not** appear here.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js
git commit -m "feat: make Validation tab intake subsections editable (parity with Technical tab)"
```

---

### Task 10: CLAUDE.md — document the five new osctl commands

**Files:**
- Modify: `CLAUDE.md` (the mandatory osctl table, lines 13–40)

**Interfaces:**
- None (documentation only) — this is what makes the new commands part of the chat agent's known toolkit, alongside the existing `update-experiment`/`create-memo`/`add-feature` rows. The chat agent's Bash tool is already unrestricted across all `python -m dashboard.osctl:*` subcommands (`dashboard/chat_session.py`), so this task is pure discoverability, not a capability change.

- [ ] **Step 1: Add table rows**

In `CLAUDE.md`, find the row:
```
| Experiment patch | `update-experiment --project <slug> --stem <stem> [--success-criteria] [--kill-criteria]` |
```
and change it to:
```
| Experiment patch/delete | `update-experiment --project <slug> --stem <stem> [--success-criteria] [--kill-criteria]` · `delete-experiment --project <slug> --stem <stem>` |
```

Find the row:
```
| Strategy memo | `create-memo --project <slug> --type <memo-type> [--summary] [--recommendation]` |
```
and change it to:
```
| Strategy memo | `create-memo --project <slug> --type <memo-type> [--summary] [--recommendation]` · `update-memo --project <slug> --type <memo-type> --version <N> [--summary] [--recommendation]` (patches that version in place — does not create a new one) · `delete-memo --project <slug> --type <memo-type> --version <N>` |
```

Find the row:
```
| Roadmap feature | `add-feature --product <prod-slug> --title "..." [--section Next]` |
```
and change it to:
```
| Roadmap feature | `add-feature --product <prod-slug> --title "..." [--section Next]` · `update-feature --product <prod-slug> --id <feature-id> [--title] [--why] [--section] [--priority]` · `delete-feature --product <prod-slug> --id <feature-id>` |
```

- [ ] **Step 2: Verify the table still renders correctly**

Run: `grep -n "update-memo\|delete-memo\|delete-experiment\|update-feature\|delete-feature" CLAUDE.md`
Expected: all five new commands appear, each on the correct existing table row (not new rows — keeps the table's row count stable)

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document update-memo/delete-memo/delete-experiment/update-feature/delete-feature in the osctl table"
```

---

### Task 11: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass, including every test added in Tasks 1–5 and the pre-existing suite (no regressions from the `add_feature` refactor in Task 3 or the `renderFileCard`/`filterIntakeSections` deletion in Task 9)

- [ ] **Step 2: Run the public-repo usage-data guard**

Run: `python -m pytest tests/test_no_usage_data.py -v`
Expected: passes — confirms no real venture/profile names leaked into any file touched across all 10 tasks

- [ ] **Step 3: Manual end-to-end pass in the browser**

Start the dashboard (`python3 dashboard/server.py`) and, on one real project, do one full add → edit → delete cycle for each of the three artifact types (memo, experiment, feature) plus one edit on an intake subsection — confirming the dashboard UI, not just the test suite, since this repo has no JS test harness and UI correctness can only be confirmed by driving it.

- [ ] **Step 4: Final commit (if Step 3 surfaced fixes)**

Only if manual verification in Step 3 required code changes:
```bash
git add -A
git commit -m "fix: address issues found in end-to-end CRUD parity verification"
```
