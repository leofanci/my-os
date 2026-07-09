# Multiple brief-specs and voices per profile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a profile hold multiple brief-specs and multiple voices (each tagged with a platform scope), selected manually everywhere generation happens (dashboard, chat, terminal), with the same symmetric commands for both.

**Architecture:** Move brief-spec and voice from one file each (`brief-spec.md`, `profile.md` body) to numbered files in `brief-specs/br{N}.md` and `voices/vc{N}.md`, each with a `platforms:` frontmatter tag. IDs (`pf.sec01.br1`, `br2`, … / `vc1`, `vc2`, …) are derived directly from the files on disk — no separate id counter needed, since minting a brief/voice writes its file in the same operation. Selection is always explicit (CLI flag, chat instruction, or dashboard dropdown); default is `br1`/`vc1`. A post's slot stores which `brief_id`/`voice_id` produced it.

**Tech Stack:** Python 3 stdlib (argparse, pathlib, re, json), vanilla JS dashboard (no build step), unittest.

## Global Constraints

- Selection between multiple briefs/voices is always manual — no platform auto-matching, no layered merge (confirmed with user during brainstorming).
- Default when nothing specified: `br1` / `vc1`.
- `platforms` value is validated against the profile's actual channel platforms (plus the literal value `all`) — never free text.
- Numbering is append-only: deleting `br2` never causes a later brief to reuse `br2`.
- `brief-specs/` (profile-level specs) is a different directory from the existing `content/briefs/` (per-post generated brief JSON) — do not conflate them.
- No backwards-compat shim for `update-profile --voice` — it is removed; voice gets its own symmetric command set.
- Every existing test must still pass unless the plan explicitly says to change it.

---

## File Structure

| File | Responsibility |
|---|---|
| `core/brief_spec_util.py` (modify) | brief-spec file I/O, now `brief_id`-aware, platform frontmatter, migration, id listing/minting |
| `core/voice_util.py` (new) | same shape as `brief_spec_util.py`, for voices |
| `core/ids.py` (modify) | lookup keys + `IdRegistry.build` loop over however many briefs/voices exist; drop `voice`/`brief-spec` from `PROFILE_META` |
| `dashboard/fileops.py` (modify) | CRUD wrappers (`create_brief_spec`, `update_brief_spec`, `delete_brief_spec`, `list_brief_specs`, and the voice equivalents); `read_profile`/`update_profile`/`create_profile` drop the single voice field; post slot gains `brief_id`/`voice_id` |
| `dashboard/osctl.py` (modify) | CLI subcommands: `create-brief-spec`, `update-brief-spec` (add `--id`/`--platforms`), `delete-brief-spec`, `get-brief-spec` (add `--id`), `create-voice`, `update-voice`, `delete-voice`, `get-voice`; remove `--voice` from `update-profile` |
| `dashboard/server.py` (modify) | HTTP routes mirroring the CLI |
| `generate.py` (modify) | `build_voice_cascade` takes `voice_id`; `do_brief`/`do_plan` resolve `brief_id`/`voice_id`; CLI flags `--spec`/`--voice` on `brief`, per-brief/per-voice counts on `plan` |
| `dashboard/app.js` + `dashboard/os-ids.js` (modify) | Profile Setup panel: repeatable brief/voice rows with platform chip + add/delete |
| `dashboard/ai_rules.py` (modify) | `BRIEF_SPEC`, `WRITES_TABLE`, `MUTATION_CMDS` docs updated for the new command surface |
| `CLAUDE.md` (modify) | keep terminal-facing docs in sync (generated from `ai_rules.py` per existing convention — see `tests/test_brief_spec_sync.py`) |

---

### Task 1: Brief-spec and voice file storage (core layer)

**Files:**
- Modify: `core/brief_spec_util.py`
- Create: `core/voice_util.py`
- Test: `tests/test_brief_spec_util.py` (extend), `tests/test_voice_util.py` (new)

**Interfaces:**
- Produces: `brief_spec_util.spec_file(profile_dir, brief_id="br1") -> Path`, `read_spec_text(profile_dir, brief_id="br1") -> str`, `read_spec_platforms(profile_dir, brief_id="br1") -> str`, `write_spec_text(profile_dir, text, brief_id="br1", platforms=None) -> None`, `list_brief_ids(profile_dir) -> list[str]`, `next_brief_id(profile_dir) -> str`, `delete_brief(profile_dir, brief_id) -> None` (raises `ValueError` if it's the only one left).
- Produces (mirrored in `voice_util.py`): `voice_file`, `read_voice_text`, `read_voice_platforms`, `write_voice_text`, `list_voice_ids`, `next_voice_id`, `delete_voice`.
- Consumed by: Task 2 (`core/ids.py`), Task 3 (`dashboard/fileops.py`), Task 7 (`generate.py`).

- [ ] **Step 1: Write failing tests for brief-spec storage**

Add to `tests/test_brief_spec_util.py`:

```python
class BriefSpecStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profile"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_default_br1(self):
        write_spec_text(self.profile_dir, "Captions under 100 words.")
        self.assertEqual(read_spec_text(self.profile_dir).strip(), "Captions under 100 words.")
        self.assertEqual(read_spec_platforms(self.profile_dir), "all")
        self.assertTrue((self.profile_dir / "brief-specs" / "br1.md").is_file())

    def test_write_and_read_second_brief_with_platforms(self):
        write_spec_text(self.profile_dir, "TikTok: under 40 words.", brief_id="br2", platforms="tiktok")
        self.assertEqual(read_spec_text(self.profile_dir, "br2").strip(), "TikTok: under 40 words.")
        self.assertEqual(read_spec_platforms(self.profile_dir, "br2"), "tiktok")
        # br1 unaffected
        self.assertEqual(read_spec_text(self.profile_dir, "br1").strip(), "")

    def test_update_without_platforms_preserves_existing_tag(self):
        write_spec_text(self.profile_dir, "v1", brief_id="br1", platforms="instagram")
        write_spec_text(self.profile_dir, "v2", brief_id="br1")  # no platforms arg
        self.assertEqual(read_spec_platforms(self.profile_dir, "br1"), "instagram")
        self.assertEqual(read_spec_text(self.profile_dir, "br1").strip(), "v2")

    def test_list_brief_ids_always_includes_br1(self):
        self.assertEqual(list_brief_ids(self.profile_dir), ["br1"])
        write_spec_text(self.profile_dir, "x", brief_id="br3")
        self.assertEqual(list_brief_ids(self.profile_dir), ["br1", "br3"])

    def test_next_brief_id_skips_occupied_and_never_reuses(self):
        self.assertEqual(next_brief_id(self.profile_dir), "br2")  # br1 implicit, so next is br2
        write_spec_text(self.profile_dir, "x", brief_id="br2")
        self.assertEqual(next_brief_id(self.profile_dir), "br3")
        delete_brief(self.profile_dir, "br2")
        self.assertEqual(next_brief_id(self.profile_dir), "br3")  # br2 never reused

    def test_delete_brief_rejects_last_one(self):
        with self.assertRaises(ValueError):
            delete_brief(self.profile_dir, "br1")

    def test_legacy_brief_spec_md_migrates_on_first_touch(self):
        (self.profile_dir / "brief-spec.md").write_text("Legacy rules.", encoding="utf-8")
        self.assertEqual(read_spec_text(self.profile_dir).strip(), "Legacy rules.")
        self.assertEqual(read_spec_platforms(self.profile_dir), "all")
        self.assertFalse((self.profile_dir / "brief-spec.md").exists())
        self.assertTrue((self.profile_dir / "brief-specs" / "br1.md").is_file())
```

Update the import block at the top of `tests/test_brief_spec_util.py` to add:

```python
from core.brief_spec_util import (
    delete_brief,
    list_brief_ids,
    next_brief_id,
    read_spec_platforms,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brief_spec_util.py -v`
Expected: FAIL — `ImportError` (names don't exist yet) or `AttributeError`.

- [ ] **Step 3: Implement brief-spec storage in `core/brief_spec_util.py`**

Replace the top of the file (lines 1-25, everything before `format_for_brief_prompt`) with:

```python
"""Profile brief-specs — projects/<project>/profiles/<profile>/brief-specs/br{N}.md

A profile can have several brief-specs, each optionally tagged to a platform
subset via `platforms:` frontmatter (or the literal value "all"). Selection
between them is always explicit (CLI flag / chat instruction / dashboard
dropdown) — this module never auto-picks one for you. br1 is the implicit
default: it's always a valid id even before anyone has written to it.

Numbering is derived straight from the files on disk (no separate counter):
minting a new brief-spec writes its file in the same operation, so there's no
chicken-and-egg problem the way there is for post ids.
"""
import re
from pathlib import Path

SPEC_DIR = "brief-specs"
LEGACY_SPEC_FILENAME = "brief-spec.md"
DEFAULT_BRIEF_ID = "br1"
_BR_RE = re.compile(r"^br(\d+)\.md$")


def _migrate_legacy_spec(profile_dir: Path) -> None:
    """One-time move of the old single brief-spec.md into brief-specs/br1.md."""
    legacy = profile_dir / LEGACY_SPEC_FILENAME
    spec_dir = profile_dir / SPEC_DIR
    if not legacy.is_file() or spec_dir.is_dir():
        return
    spec_dir.mkdir(parents=True, exist_ok=True)
    text = legacy.read_text(encoding="utf-8").strip()
    (spec_dir / "br1.md").write_text(f"---\nplatforms: all\n---\n{text}\n", encoding="utf-8")
    legacy.unlink()


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = {}
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            return fm, parts[2].strip()
    return {}, text.strip()


def spec_file(profile_dir: Path, brief_id: str = DEFAULT_BRIEF_ID) -> Path:
    _migrate_legacy_spec(profile_dir)
    return profile_dir / SPEC_DIR / f"{brief_id}.md"


def read_spec_text(profile_dir: Path, brief_id: str = DEFAULT_BRIEF_ID) -> str:
    """Load the live brief spec from disk (always read at job time — never cache)."""
    f = spec_file(profile_dir, brief_id)
    if not f.exists():
        return ""
    _, body = _split_frontmatter(f.read_text(encoding="utf-8"))
    return body


def read_spec_platforms(profile_dir: Path, brief_id: str = DEFAULT_BRIEF_ID) -> str:
    f = spec_file(profile_dir, brief_id)
    if not f.exists():
        return "all"
    fm, _ = _split_frontmatter(f.read_text(encoding="utf-8"))
    return fm.get("platforms", "all")


def write_spec_text(profile_dir: Path, text: str, brief_id: str = DEFAULT_BRIEF_ID,
                     platforms: str | None = None) -> None:
    """Persist a brief spec. platforms=None keeps whatever tag it already had
    (or "all" for a brand new one) — update-brief-spec without --platforms
    must not silently reset the tag."""
    f = spec_file(profile_dir, brief_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    if platforms is None:
        platforms = read_spec_platforms(profile_dir, brief_id) if f.exists() else "all"
    body = (text or "").strip()
    f.write_text(f"---\nplatforms: {platforms}\n---\n{body}\n", encoding="utf-8")


def list_brief_ids(profile_dir: Path) -> list[str]:
    """Every brief id for this profile, br1 first — br1 is always included
    even if nobody has written to it yet."""
    _migrate_legacy_spec(profile_dir)
    nums = {1}
    d = profile_dir / SPEC_DIR
    if d.is_dir():
        for f in d.iterdir():
            m = _BR_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return [f"br{n}" for n in sorted(nums)]


def next_brief_id(profile_dir: Path) -> str:
    """Next free brief id — br1 counts as occupied even before it has a file,
    so the first create-brief-spec call always mints br2, not a duplicate br1."""
    _migrate_legacy_spec(profile_dir)
    nums = {1}
    d = profile_dir / SPEC_DIR
    if d.is_dir():
        for f in d.iterdir():
            m = _BR_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return f"br{max(nums) + 1}"


def delete_brief(profile_dir: Path, brief_id: str) -> None:
    ids = list_brief_ids(profile_dir)
    if len(ids) <= 1:
        raise ValueError("cannot delete the only remaining brief-spec")
    if brief_id not in ids:
        raise ValueError(f"brief '{brief_id}' not found")
    f = profile_dir / SPEC_DIR / f"{brief_id}.md"
    if f.exists():
        f.unlink()
```

Leave everything from `format_for_brief_prompt` onward unchanged (identity fields, spec-field parsing, brief validation logic are untouched by this feature).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brief_spec_util.py -v`
Expected: PASS (all, including the pre-existing tests in this file — `read_spec_text`/`write_spec_text` keep their old 2-positional-arg call shape working via defaults).

- [ ] **Step 5: Write `core/voice_util.py` mirroring the same shape**

Create `tests/test_voice_util.py`:

```python
import tempfile
import unittest
from pathlib import Path

from core.voice_util import (
    delete_voice,
    list_voice_ids,
    next_voice_id,
    read_voice_platforms,
    read_voice_text,
    write_voice_text,
)


class VoiceStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profile"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_default_vc1(self):
        write_voice_text(self.profile_dir, "Warm, direct, no corporate speak.")
        self.assertEqual(read_voice_text(self.profile_dir).strip(), "Warm, direct, no corporate speak.")
        self.assertEqual(read_voice_platforms(self.profile_dir), "all")

    def test_second_voice_with_platform_tag(self):
        write_voice_text(self.profile_dir, "Faster cuts, slang okay.", voice_id="vc2", platforms="tiktok")
        self.assertEqual(read_voice_text(self.profile_dir, "vc2").strip(), "Faster cuts, slang okay.")
        self.assertEqual(read_voice_platforms(self.profile_dir, "vc2"), "tiktok")

    def test_list_and_next_id(self):
        self.assertEqual(list_voice_ids(self.profile_dir), ["vc1"])
        self.assertEqual(next_voice_id(self.profile_dir), "vc2")
        write_voice_text(self.profile_dir, "x", voice_id="vc2")
        self.assertEqual(list_voice_ids(self.profile_dir), ["vc1", "vc2"])
        self.assertEqual(next_voice_id(self.profile_dir), "vc3")

    def test_delete_rejects_last_one(self):
        with self.assertRaises(ValueError):
            delete_voice(self.profile_dir, "vc1")

    def test_legacy_profile_body_migrates_on_first_touch(self):
        (self.profile_dir / "profile.md").write_text(
            "---\nname: Demo\ntopic: film\nproject: acme\n---\nLegacy voice text.\n",
            encoding="utf-8",
        )
        self.assertEqual(read_voice_text(self.profile_dir).strip(), "Legacy voice text.")
        # profile.md frontmatter untouched, body cleared
        text = (self.profile_dir / "profile.md").read_text(encoding="utf-8")
        self.assertIn("name: Demo", text)
        self.assertNotIn("Legacy voice text.", text)
```

Run: `python -m pytest tests/test_voice_util.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.voice_util'`.

- [ ] **Step 6: Implement `core/voice_util.py`**

```python
"""Profile voices — projects/<project>/profiles/<profile>/voices/vc{N}.md

Same shape as core/brief_spec_util.py's brief-spec storage: several voices
per profile, each tagged with a platforms scope, selected explicitly, never
auto-matched. vc1 is the implicit default.

Legacy migration: a profile's voice used to be profile.md's body. On first
touch, that body moves into voices/vc1.md (platforms: all) and profile.md
keeps only its frontmatter (name/topic/project).
"""
import re
from pathlib import Path

VOICE_DIR = "voices"
DEFAULT_VOICE_ID = "vc1"
_VC_RE = re.compile(r"^vc(\d+)\.md$")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = {}
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            return fm, parts[2].strip()
    return {}, text.strip()


def _migrate_legacy_voice(profile_dir: Path) -> None:
    """One-time move of profile.md's body into voices/vc1.md."""
    profile_md = profile_dir / "profile.md"
    voice_dir = profile_dir / VOICE_DIR
    if not profile_md.is_file() or voice_dir.is_dir():
        return
    fm, body = _split_frontmatter(profile_md.read_text(encoding="utf-8"))
    if not body.strip():
        return
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "vc1.md").write_text(f"---\nplatforms: all\n---\n{body}\n", encoding="utf-8")
    fm_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    profile_md.write_text(f"---\n{fm_lines}\n---\n", encoding="utf-8")


def voice_file(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> Path:
    _migrate_legacy_voice(profile_dir)
    return profile_dir / VOICE_DIR / f"{voice_id}.md"


def read_voice_text(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    f = voice_file(profile_dir, voice_id)
    if not f.exists():
        return ""
    _, body = _split_frontmatter(f.read_text(encoding="utf-8"))
    return body


def read_voice_platforms(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    f = voice_file(profile_dir, voice_id)
    if not f.exists():
        return "all"
    fm, _ = _split_frontmatter(f.read_text(encoding="utf-8"))
    return fm.get("platforms", "all")


def write_voice_text(profile_dir: Path, text: str, voice_id: str = DEFAULT_VOICE_ID,
                      platforms: str | None = None) -> None:
    f = voice_file(profile_dir, voice_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    if platforms is None:
        platforms = read_voice_platforms(profile_dir, voice_id) if f.exists() else "all"
    body = (text or "").strip()
    f.write_text(f"---\nplatforms: {platforms}\n---\n{body}\n", encoding="utf-8")


def list_voice_ids(profile_dir: Path) -> list[str]:
    _migrate_legacy_voice(profile_dir)
    nums = {1}
    d = profile_dir / VOICE_DIR
    if d.is_dir():
        for f in d.iterdir():
            m = _VC_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return [f"vc{n}" for n in sorted(nums)]


def next_voice_id(profile_dir: Path) -> str:
    _migrate_legacy_voice(profile_dir)
    nums = {1}
    d = profile_dir / VOICE_DIR
    if d.is_dir():
        for f in d.iterdir():
            m = _VC_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return f"vc{max(nums) + 1}"


def delete_voice(profile_dir: Path, voice_id: str) -> None:
    ids = list_voice_ids(profile_dir)
    if len(ids) <= 1:
        raise ValueError("cannot delete the only remaining voice")
    if voice_id not in ids:
        raise ValueError(f"voice '{voice_id}' not found")
    f = profile_dir / VOICE_DIR / f"{voice_id}.md"
    if f.exists():
        f.unlink()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_util.py tests/test_brief_spec_util.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/brief_spec_util.py core/voice_util.py tests/test_brief_spec_util.py tests/test_voice_util.py
git commit -m "feat: numbered, platform-tagged brief-specs and voices per profile (core storage)"
```

---

### Task 2: ID registry — numbered br/vc ids

**Files:**
- Modify: `core/ids.py`
- Test: `tests/test_ids.py` (extend + fix existing assertions)

**Interfaces:**
- Consumes: `core.brief_spec_util.list_brief_ids(profile_dir)`, `core.voice_util.list_voice_ids(profile_dir)` (Task 1).
- Produces: `lk_prof_brief_spec(profile, brief_id="br1") -> str`, `lk_prof_voice(profile, voice_id="vc1") -> str` (signature changed — now takes an id). `IdRegistry.build` registers one composed id per existing brief/voice instead of exactly one of each.

- [ ] **Step 1: Update the two existing assertions that assumed exactly one br/vc**

In `tests/test_ids.py`, `test_registry_profile_and_slot_fields` (around line 87-88), change:

```python
            self.assertEqual(reg.get("brief-spec:prof:demo"), "pr1.pf1.sec01.br1")
            self.assertEqual(reg.get("voice:prof:demo"), "pr1.pf1.sec01.vc1")
```

to:

```python
            self.assertEqual(reg.get(lk_prof_brief_spec("demo")), "pr1.pf1.sec01.br1")
            self.assertEqual(reg.get(lk_prof_voice("demo")), "pr1.pf1.sec01.vc1")
```

Add `lk_prof_brief_spec, lk_prof_voice` to the `from core.ids import (...)` block at the top of the file.

- [ ] **Step 2: Add a new failing test for multiple briefs/voices**

Append to `tests/test_ids.py`:

```python
    def test_registry_multiple_briefs_and_voices(self):
        tree = [{
            "slug": "acme", "name": "Acme",
            "profiles": [{"slug": "demo", "name": "Demo", "channels": []}],
            "products": [],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "projects" / "acme" / "profiles" / "demo"
            (profile_dir / "brief-specs").mkdir(parents=True)
            (profile_dir / "brief-specs" / "br2.md").write_text("---\nplatforms: tiktok\n---\nx\n", encoding="utf-8")
            (profile_dir / "voices").mkdir(parents=True)
            (profile_dir / "voices" / "vc2.md").write_text("---\nplatforms: all\n---\ny\n", encoding="utf-8")
            reg = build_id_registry(tree, [], root=root)
            self.assertEqual(reg.get(lk_prof_brief_spec("demo", "br1")), "pr1.pf1.sec01.br1")
            self.assertEqual(reg.get(lk_prof_brief_spec("demo", "br2")), "pr1.pf1.sec01.br2")
            self.assertEqual(reg.get(lk_prof_voice("demo", "vc1")), "pr1.pf1.sec01.vc1")
            self.assertEqual(reg.get(lk_prof_voice("demo", "vc2")), "pr1.pf1.sec01.vc2")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_ids.py -v`
Expected: FAIL — `test_registry_multiple_briefs_and_voices` errors (`lk_prof_brief_spec("demo", "br2")` — TypeError, function takes 1 positional arg today). The updated assertions in `test_registry_profile_and_slot_fields` pass already (no signature change yet) but will be revisited once Step 4 lands.

- [ ] **Step 4: Update `core/ids.py`**

Replace `lk_prof_brief_spec`/`lk_prof_voice` (lines 212-217):

```python
def lk_prof_brief_spec(profile: str, brief_id: str = "br1") -> str:
    return f"brief-spec:prof:{profile}:{brief_id}"


def lk_prof_voice(profile: str, voice_id: str = "vc1") -> str:
    return f"voice:prof:{profile}:{voice_id}"
```

Add imports near the top of the file (after the existing `from core.project_schemas import ...` / `from core.subsections import ...` block):

```python
from core.brief_spec_util import list_brief_ids
from core.voice_util import list_voice_ids
```

Replace the setup-tab block in `IdRegistry.build` (lines 483-491):

```python
                setup_tab_id = f"{pf_id}.sec{PROF_TAB_NUM['setup']}"
                br_spec_id = f"{setup_tab_id}.br1"
                reg._add(br_spec_id, "brief spec", kind="brief_spec", parent=setup_tab_id,
                         ref={"profile": prf_slug, "field": "brief-spec"})
                reg._bind(lk_prof_brief_spec(prf_slug), br_spec_id)
                voice_id = f"{setup_tab_id}.vc1"
                reg._add(voice_id, "voice", kind="voice", parent=setup_tab_id,
                         ref={"profile": prf_slug, "field": "voice"})
                reg._bind(lk_prof_voice(prf_slug), voice_id)
```

with:

```python
                setup_tab_id = f"{pf_id}.sec{PROF_TAB_NUM['setup']}"
                prof_dir = (root / "projects" / pslug / "profiles" / prf_slug) if root else None
                brief_ids = list_brief_ids(prof_dir) if prof_dir and prof_dir.is_dir() else ["br1"]
                for bid in brief_ids:
                    br_cid = f"{setup_tab_id}.{bid}"
                    reg._add(br_cid, "brief spec", kind="brief_spec", parent=setup_tab_id,
                             ref={"profile": prf_slug, "field": "brief-spec", "brief_id": bid})
                    reg._bind(lk_prof_brief_spec(prf_slug, bid), br_cid)
                voice_ids = list_voice_ids(prof_dir) if prof_dir and prof_dir.is_dir() else ["vc1"]
                for vid in voice_ids:
                    vc_cid = f"{setup_tab_id}.{vid}"
                    reg._add(vc_cid, "voice", kind="voice", parent=setup_tab_id,
                             ref={"profile": prf_slug, "field": "voice", "voice_id": vid})
                    reg._bind(lk_prof_voice(prf_slug, vid), vc_cid)
```

Update `PROFILE_META` (line 132) to drop the two fields that are no longer profile identity metadata:

```python
PROFILE_META = ("name", "topic")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ids.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full existing test suite to catch any other caller of the old 1-arg lookup signature**

Run: `python -m pytest tests/ -x -q`
Expected: any failures here are calls elsewhere in the codebase (not yet updated by this plan) using `lk_prof_brief_spec(slug)` / `lk_prof_voice(slug)` positionally — since both keep a default second arg, these should already pass. Confirm no failures before moving on; if any surface, note the file/line for a quick follow-up fix in this same task.

- [ ] **Step 7: Commit**

```bash
git add core/ids.py tests/test_ids.py
git commit -m "feat: id registry supports N brief-specs and N voices per profile"
```

---

### Task 3: fileops CRUD for brief-specs and voices; drop single voice from profile identity

**Files:**
- Modify: `dashboard/fileops.py`
- Test: `tests/test_fileops_posts.py` (extend), new `tests/test_fileops_briefs_voices.py`

**Interfaces:**
- Consumes: Task 1's `core.brief_spec_util` / `core.voice_util` functions.
- Produces: `fileops.profile_platforms(slug) -> list[str]`, `fileops.list_brief_specs(slug) -> list[dict]`, `fileops.create_brief_spec(slug, text, platforms="all") -> dict`, `fileops.update_brief_spec(slug, text, brief_id="br1", platforms=None) -> dict` (replaces old 2-arg `write_brief_spec`), `fileops.delete_brief_spec(slug, brief_id) -> dict`, `fileops.get_brief_spec(slug, brief_id="br1") -> dict`, and voice equivalents `list_voices`, `create_voice`, `update_voice`, `delete_voice`, `get_voice`. `read_profile(slug)` no longer returns `voice`/`brief_spec` keys (moved to the new list endpoints). `create_profile`/`update_profile` drop the `voice` field entirely.

- [ ] **Step 1: Write failing tests**

Create `tests/test_fileops_briefs_voices.py`:

```python
import tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db


class BriefsVoicesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-ig" / "channel.md", "---\nplatform: instagram\n---")
        write(prof / "channels" / "demo-tt" / "channel.md", "---\nplatform: tiktok\n---")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_platforms_lists_channel_platforms(self):
        self.assertEqual(sorted(fileops.profile_platforms("demo")), ["instagram", "tiktok"])

    def test_create_brief_spec_mints_br2_and_validates_platform(self):
        res = fileops.create_brief_spec("demo", "TikTok only rules.", platforms="tiktok")
        self.assertEqual(res["brief_id"], "br2")
        with self.assertRaises(fileops.ActionError):
            fileops.create_brief_spec("demo", "bad", platforms="youtube")

    def test_update_brief_spec_defaults_to_br1(self):
        fileops.update_brief_spec("demo", "Default rules.")
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Default rules.")

    def test_list_brief_specs(self):
        fileops.create_brief_spec("demo", "second", platforms="tiktok")
        specs = fileops.list_brief_specs("demo")
        self.assertEqual([s["id"] for s in specs], ["br1", "br2"])
        self.assertEqual(specs[1]["platforms"], "tiktok")

    def test_delete_brief_spec_guards_last_one(self):
        with self.assertRaises(fileops.ActionError):
            fileops.delete_brief_spec("demo", "br1")

    def test_create_and_list_voice(self):
        fileops.create_voice("demo", "Faster cuts.", platforms="tiktok")
        voices = fileops.list_voices("demo")
        self.assertEqual([v["id"] for v in voices], ["vc1", "vc2"])

    def test_read_profile_no_longer_returns_voice_or_brief_spec(self):
        prof = fileops.read_profile("demo")
        self.assertNotIn("voice", prof)
        self.assertNotIn("brief_spec", prof)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fileops_briefs_voices.py -v`
Expected: FAIL — `AttributeError: module 'dashboard.fileops' has no attribute 'profile_platforms'` etc.

- [ ] **Step 3: Update imports in `dashboard/fileops.py`**

Change the existing `from core.brief_spec_util import (...)` block near the top to add the new names:

```python
from core.brief_spec_util import (
    delete_brief,
    list_brief_ids,
    next_brief_id,
    read_spec_platforms,
    read_spec_text,
    write_spec_text,
)
from core.voice_util import (
    delete_voice as _delete_voice_file,
    list_voice_ids,
    next_voice_id,
    read_voice_platforms,
    read_voice_text,
    write_voice_text,
)
```

(Existing call sites already import `read_spec_text`, `write_spec_text`, `format_for_brief_prompt`, `merge_fields_from_slot`, `normalize_brief_for_spec`, `validate_brief_obj` — keep those, just add the new names to the same import.)

- [ ] **Step 4: Add `profile_platforms` helper**

Add near `_channel_dir` (after it, ~line 144):

```python
def profile_platforms(slug: str) -> list[str]:
    """Every distinct platform among this profile's channels (for validating
    a brief-spec/voice's `platforms` tag against what actually exists)."""
    profile_dir = _profile_dir(slug)
    channels_dir = profile_dir / "channels"
    if not channels_dir.is_dir():
        return []
    platforms = []
    for channel_dir in sorted(channels_dir.iterdir()):
        channel_md = channel_dir / "channel.md"
        if not channel_md.is_file():
            continue
        fm, _ = _parse_frontmatter(channel_md.read_text(encoding="utf-8"))
        p = fm.get("platform", "").strip()
        if p and p not in platforms:
            platforms.append(p)
    return platforms


def _validate_platforms_tag(slug: str, platforms: str) -> None:
    platforms = (platforms or "all").strip()
    if platforms == "all":
        return
    valid = set(profile_platforms(slug))
    requested = {p.strip() for p in platforms.split(",") if p.strip()}
    unknown = requested - valid
    if unknown:
        raise ActionError(
            f"unknown platform(s) {sorted(unknown)} for profile '{slug}' — "
            f"this profile's channels are: {sorted(valid) or '(none)'}"
        )
```

- [ ] **Step 5: Replace the brief-spec section (lines 331-344) with the full CRUD set**

```python
def brief_spec_relpath(slug, brief_id="br1"):
    """Repo-relative path to one of the profile's brief-spec files."""
    profile_dir = _profile_dir(slug)
    return str((profile_dir / "brief-specs" / f"{brief_id}.md").relative_to(ROOT))


def read_brief_spec(slug, brief_id="br1"):
    """Live brief spec text for this profile + id (default br1)."""
    return read_spec_text(_profile_dir(slug), brief_id)


def get_brief_spec(slug: str, brief_id: str = "br1") -> dict:
    profile_dir = _profile_dir(slug)
    return {
        "slug": slug, "id": brief_id,
        "path": brief_spec_relpath(slug, brief_id),
        "text": read_spec_text(profile_dir, brief_id),
        "platforms": read_spec_platforms(profile_dir, brief_id),
    }


def list_brief_specs(slug: str) -> list[dict]:
    profile_dir = _profile_dir(slug)
    return [get_brief_spec(slug, bid) for bid in list_brief_ids(profile_dir)]


def write_brief_spec(slug, text, brief_id="br1", platforms=None):
    """Write one brief-spec file. Profile Setup and chat use this same path."""
    profile_dir = _profile_dir(slug)
    if platforms is not None:
        _validate_platforms_tag(slug, platforms)
    write_spec_text(profile_dir, text, brief_id, platforms)
    return {"slug": slug, "id": brief_id, "path": brief_spec_relpath(slug, brief_id)}


# Back-compat name used by existing callers that pass no id (Profile Setup,
# older osctl behavior) — same as write_brief_spec with brief_id="br1".
def update_brief_spec(slug, text, brief_id="br1", platforms=None):
    return write_brief_spec(slug, text, brief_id, platforms)


def create_brief_spec(slug: str, text: str, platforms: str = "all") -> dict:
    profile_dir = _profile_dir(slug)
    _validate_platforms_tag(slug, platforms)
    brief_id = next_brief_id(profile_dir)
    write_spec_text(profile_dir, text, brief_id, platforms)
    return {"slug": slug, "brief_id": brief_id, "path": brief_spec_relpath(slug, brief_id)}


def delete_brief_spec(slug: str, brief_id: str) -> dict:
    profile_dir = _profile_dir(slug)
    try:
        delete_brief(profile_dir, brief_id)
    except ValueError as e:
        raise ActionError(str(e)) from e
    return {"slug": slug, "brief_id": brief_id, "deleted": True}
```

- [ ] **Step 6: Add the voice CRUD set (new, near `update_profile` ~line 747) and strip voice out of profile identity**

```python
def get_voice(slug: str, voice_id: str = "vc1") -> dict:
    profile_dir = _profile_dir(slug)
    return {
        "slug": slug, "id": voice_id,
        "text": read_voice_text(profile_dir, voice_id),
        "platforms": read_voice_platforms(profile_dir, voice_id),
    }


def list_voices(slug: str) -> list[dict]:
    profile_dir = _profile_dir(slug)
    return [get_voice(slug, vid) for vid in list_voice_ids(profile_dir)]


def create_voice(slug: str, text: str, platforms: str = "all") -> dict:
    profile_dir = _profile_dir(slug)
    _validate_platforms_tag(slug, platforms)
    voice_id = next_voice_id(profile_dir)
    write_voice_text(profile_dir, text, voice_id, platforms)
    return {"slug": slug, "voice_id": voice_id}


def update_voice(slug: str, text: str, voice_id: str = "vc1", platforms: str = None) -> dict:
    profile_dir = _profile_dir(slug)
    if platforms is not None:
        _validate_platforms_tag(slug, platforms)
    write_voice_text(profile_dir, text, voice_id, platforms)
    return {"slug": slug, "voice_id": voice_id}


def delete_voice(slug: str, voice_id: str) -> dict:
    profile_dir = _profile_dir(slug)
    try:
        _delete_voice_file(profile_dir, voice_id)
    except ValueError as e:
        raise ActionError(str(e)) from e
    return {"slug": slug, "voice_id": voice_id, "deleted": True}
```

Now update `read_profile` (drop `voice`/`brief_spec` — they moved to the list endpoints above):

```python
def read_profile(slug):
    """Read profile.md and return name, topic, project. Voice and brief-spec
    live in voices/ and brief-specs/ now — use list_voices/list_brief_specs."""
    d = _profile_dir(slug)
    f = d / "profile.md"
    if not f.exists():
        return {"slug": slug, "name": slug, "topic": "", "project": ""}
    fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8"))
    return {"slug": slug, "name": fm.get("name", slug),
            "topic": fm.get("topic", ""), "project": fm.get("project", "")}
```

Update `create_profile` (drop `voice` handling — line ~729-744):

```python
def create_profile(project_slug: str, slug: str, fields: dict) -> dict:
    project_dir = ROOT / "projects" / project_slug
    if not project_dir.exists():
        raise ActionError(f"project '{project_slug}' not found")
    profile_dir = project_dir / "profiles" / slug
    if profile_dir.exists():
        raise ActionError(f"profile '{slug}' already exists")
    name = (fields.get("name") or slug).strip()
    topic = (fields.get("topic") or "").strip()
    for sub in ["content/briefs", "channels"]:
        (profile_dir / sub).mkdir(parents=True, exist_ok=True)
    md = f"---\nname: {name}\ntopic: {topic}\nproject: {project_slug}\n---\n"
    (profile_dir / "profile.md").write_text(md, encoding="utf-8")
    reindex()
    return {"slug": slug, "project": project_slug}
```

Update `update_profile` (drop `voice` handling — line ~747-759):

```python
def update_profile(slug: str, fields: dict) -> dict:
    """Rewrite profile.md frontmatter (name/topic), keep structure."""
    profile_dir = _profile_dir(slug)  # raises if not found
    f = profile_dir / "profile.md"
    fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8")) if f.exists() else ({}, "")
    name = (fields.get("name") or fm.get("name") or slug).strip()
    topic = (fields.get("topic") if fields.get("topic") is not None else fm.get("topic", "")).strip()
    project = fm.get("project", "")
    md = f"---\nname: {name}\ntopic: {topic}\nproject: {project}\n---\n"
    f.write_text(md, encoding="utf-8")
    reindex()
    return {"slug": slug}
```

- [ ] **Step 7: Fix the one pre-existing test that reads `voice`/`brief_spec` off `read_profile`**

In `tests/test_fileops_posts.py`, `test_brief_spec_roundtrip` (line 75-78) currently does:

```python
    def test_brief_spec_roundtrip(self):
        fileops.write_brief_spec("demo", "Captions under 100 words.")
        self.assertEqual(fileops.read_profile("demo")["brief_spec"].strip(),
                         "Captions under 100 words.")
```

Change to read from the new source:

```python
    def test_brief_spec_roundtrip(self):
        fileops.write_brief_spec("demo", "Captions under 100 words.")
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(),
                         "Captions under 100 words.")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_fileops_briefs_voices.py tests/test_fileops_posts.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full suite to catch any other reader of `profile["voice"]` / `profile["brief_spec"]`**

Run: `python -m pytest tests/ -q`
Expected: report and fix any remaining failures (likely `dashboard/server.py` and `dashboard/app.js` still expecting the old shape — those are fixed in Tasks 5 and 8; if a *test* fails here for a reason outside this plan's scope, note it rather than silently patching unrelated behavior).

- [ ] **Step 10: Commit**

```bash
git add dashboard/fileops.py tests/test_fileops_briefs_voices.py tests/test_fileops_posts.py
git commit -m "feat: fileops CRUD for numbered brief-specs and voices; drop single voice from profile identity"
```

---

### Task 4: Post slot gains `brief_id`/`voice_id`

**Files:**
- Modify: `dashboard/fileops.py` (`add_post`, `update_post`)
- Test: `tests/test_fileops_posts.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: post slot dicts now may carry `brief_id`/`voice_id` string fields (default `"br1"`/`"vc1"` when not supplied); read back via existing `read_detail`/`db.profile_posts`.

- [ ] **Step 1: Write failing test**

Add to `tests/test_fileops_posts.py`:

```python
    def test_post_defaults_brief_and_voice_ids(self):
        fileops.add_post("demo", {"working_title": "Idea A", "channels": "demo-tiktok"})
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["brief_id"], "br1")
        self.assertEqual(post["voice_id"], "vc1")

    def test_post_can_specify_brief_and_voice_ids(self):
        fileops.add_post("demo", {
            "working_title": "Idea A", "channels": "demo-tiktok",
            "brief_id": "br2", "voice_id": "vc2",
        })
        post = db.profile_posts("demo")[0]
        self.assertEqual(post["brief_id"], "br2")
        self.assertEqual(post["voice_id"], "vc2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fileops_posts.py -k brief_and_voice -v`
Expected: FAIL — `KeyError: 'brief_id'`.

- [ ] **Step 3: Add the two fields to post handling**

In `dashboard/fileops.py`, find `_POST_FIELDS` (line 403):

```python
_POST_FIELDS = ("date", "pillar", "working_title", "concept", "format", "objective", "platform")
```

Change to:

```python
_POST_FIELDS = ("date", "pillar", "working_title", "concept", "format", "objective", "platform",
                "brief_id", "voice_id")
```

In `add_post` (around line 405-420), after the loop that copies `_POST_FIELDS` values onto `post`, add defaults:

```python
    post.setdefault("brief_id", "br1")
    post.setdefault("voice_id", "vc1")
```

(place this right before the post dict is appended/written to the plan file — check the exact surrounding lines when editing, the loop is `for k in _POST_FIELDS: ... post[k] = v`, insert the `setdefault` calls immediately after that loop, before `data["posts"].append(post)` or equivalent).

- [ ] **Step 4: Confirm `db.py`'s post projection doesn't drop unknown keys**

Read `dashboard/db.py`'s `profile_posts` (or wherever plan-slot dicts get turned into DB rows) — if it uses an explicit column allowlist, add `brief_id`/`voice_id` to it the same way `platform`/`format` are already listed. If it just passes through the dict as JSON, no change needed. Confirm which case applies before editing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fileops_posts.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/fileops.py dashboard/db.py tests/test_fileops_posts.py
git commit -m "feat: post slots track which brief/voice generated them"
```

---

### Task 5: osctl CLI commands

**Files:**
- Modify: `dashboard/osctl.py`
- Test: `tests/test_osctl.py` (extend)

**Interfaces:**
- Consumes: Task 3's fileops functions.
- Produces: subcommands `create-brief-spec`, `update-brief-spec` (now with `--id`/`--platforms`), `delete-brief-spec`, `get-brief-spec` (now with optional `--id`), `create-voice`, `update-voice`, `delete-voice`, `get-voice`. `update-profile` no longer accepts `--voice`.

- [ ] **Step 1: Write failing tests**

Check how `tests/test_osctl.py` invokes the CLI (likely via a helper that calls `_build_parser()` and runs `_run`, or subprocess). Read the file's existing pattern for `update-brief-spec` before writing new tests, then add, matching that pattern:

```python
    def test_create_and_update_brief_spec_with_id(self):
        out = self._run(["create-brief-spec", "--profile", "demo", "--text", "tiktok rules", "--platforms", "tiktok"])
        self.assertEqual(out["brief_id"], "br2")
        out2 = self._run(["update-brief-spec", "--profile", "demo", "--id", "br2", "--text", "updated"])
        self.assertTrue(out2["ok"])
        got = self._run(["get-brief-spec", "--profile", "demo", "--id", "br2"])
        self.assertEqual(got["text"].strip(), "updated")

    def test_create_and_delete_voice(self):
        out = self._run(["create-voice", "--profile", "demo", "--text", "faster cuts", "--platforms", "tiktok"])
        self.assertEqual(out["voice_id"], "vc2")
        out2 = self._run(["delete-voice", "--profile", "demo", "--id", "vc2"])
        self.assertTrue(out2["deleted"])
```

(Adapt to whatever the file's actual test-invocation helper is called — read the file first; don't guess a helper name that doesn't exist.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_osctl.py -k "brief_spec_with_id or delete_voice" -v`
Expected: FAIL — unrecognized argument / no such subcommand.

- [ ] **Step 3: Update `dashboard/osctl.py`**

Replace `update-profile`'s brief block (lines 269-275) — drop `--voice`:

```python
    p = sub.add_parser("update-profile")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--topic")
    p.set_defaults(_run=lambda a: fileops.update_profile(
        a.slug, _fields(a, ["name", "topic"])))
```

Also update `create-profile`'s parser (around line 64-71) to drop `--voice`:

```python
    p = sub.add_parser("create-profile")
    p.add_argument("--project", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--topic")
    p.set_defaults(_run=lambda a: fileops.create_profile(
        a.project, a.slug, _fields(a, ["name", "topic"])))
```

(Keep whatever other flags/lines already exist between `add_parser("create-profile")` and the `set_defaults` call that aren't shown here — only remove the `--voice` argument and its `"voice"` key in the `_fields` list.)

Replace the `get-brief-spec`/`update-brief-spec` block (lines 277-297):

```python
    p = sub.add_parser("get-brief-spec",
                       help="Read one profile brief-spec (default br1), or list all with --list")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="br1", dest="brief_id")
    p.add_argument("--list", action="store_true")
    p.set_defaults(_run=lambda a: (
        {"profile": a.profile, "specs": fileops.list_brief_specs(a.profile)}
        if a.list else fileops.get_brief_spec(a.profile, a.brief_id)
    ))

    p = sub.add_parser("update-brief-spec",
                       help="Replace one profile brief-spec (default br1)")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="br1", dest="brief_id")
    p.add_argument("--platforms")
    p.add_argument("--text", default="")
    def _update_brief_spec(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("brief spec text required (--text or stdin)")
        return fileops.write_brief_spec(a.profile, text, a.brief_id, a.platforms)
    p.set_defaults(_run=_update_brief_spec)

    p = sub.add_parser("create-brief-spec",
                       help="Add a new brief-spec to a profile (mints the next br id)")
    p.add_argument("--profile", required=True)
    p.add_argument("--platforms", default="all")
    p.add_argument("--text", default="")
    def _create_brief_spec(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("brief spec text required (--text or stdin)")
        return fileops.create_brief_spec(a.profile, text, a.platforms)
    p.set_defaults(_run=_create_brief_spec)

    p = sub.add_parser("delete-brief-spec", help="Delete a profile brief-spec by id")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", required=True, dest="brief_id")
    p.set_defaults(_run=lambda a: fileops.delete_brief_spec(a.profile, a.brief_id))

    p = sub.add_parser("get-voice",
                       help="Read one profile voice (default vc1), or list all with --list")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="vc1", dest="voice_id")
    p.add_argument("--list", action="store_true")
    p.set_defaults(_run=lambda a: (
        {"profile": a.profile, "voices": fileops.list_voices(a.profile)}
        if a.list else fileops.get_voice(a.profile, a.voice_id)
    ))

    p = sub.add_parser("update-voice", help="Replace one profile voice (default vc1)")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="vc1", dest="voice_id")
    p.add_argument("--platforms")
    p.add_argument("--text", default="")
    def _update_voice(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("voice text required (--text or stdin)")
        return fileops.update_voice(a.profile, text, a.voice_id, a.platforms)
    p.set_defaults(_run=_update_voice)

    p = sub.add_parser("create-voice", help="Add a new voice to a profile (mints the next vc id)")
    p.add_argument("--profile", required=True)
    p.add_argument("--platforms", default="all")
    p.add_argument("--text", default="")
    def _create_voice(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("voice text required (--text or stdin)")
        return fileops.create_voice(a.profile, text, a.platforms)
    p.set_defaults(_run=_create_voice)

    p = sub.add_parser("delete-voice", help="Delete a profile voice by id")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", required=True, dest="voice_id")
    p.set_defaults(_run=lambda a: fileops.delete_voice(a.profile, a.voice_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_osctl.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/osctl.py tests/test_osctl.py
git commit -m "feat: osctl commands for multiple brief-specs and voices per profile"
```

---

### Task 6: Dashboard HTTP routes

**Files:**
- Modify: `dashboard/server.py`
- Test: `tests/test_server_ask.py` or the file with existing server route tests (check which file covers `/api/profile/*` routes — read before adding)

**Interfaces:**
- Consumes: Task 3's fileops functions.
- Produces: `GET /api/profile/<slug>/brief-specs` (list), `POST /api/profile/<slug>/brief-specs` (create), `PUT /api/profile/<slug>/brief-specs/<id>` (update), `DELETE /api/profile/<slug>/brief-specs/<id>` (delete); same four for `/api/profile/<slug>/voices`.

- [ ] **Step 1: Read the existing route-handling structure around `/api/profile/`**

Read `dashboard/server.py` lines 615-660 (GET/PUT dispatch for `/api/profile/...`) to match the existing `if path.startswith(...) and path.endswith(...)` style exactly before adding new branches.

- [ ] **Step 2: Write failing tests**

In the test file covering server routes (identify by grepping for `"/api/profile/"` in `tests/`), add:

```python
    def test_brief_specs_list_create_update_delete(self):
        # adapt to this file's existing request-helper pattern (e.g. self._get/_post/_put/_delete)
        specs = self._get(f"/api/profile/demo/brief-specs")
        self.assertEqual(len(specs["specs"]), 1)
        created = self._post(f"/api/profile/demo/brief-specs", {"text": "tiktok rules", "platforms": "tiktok"})
        self.assertEqual(created["brief_id"], "br2")
        self._put(f"/api/profile/demo/brief-specs/br2", {"text": "updated"})
        got = self._get(f"/api/profile/demo/brief-specs/br2")
        self.assertEqual(got["text"].strip(), "updated")
        self._delete(f"/api/profile/demo/brief-specs/br2")
```

(Match this project's actual test helper method names — read the file first rather than inventing `_get`/`_post`/`_put`/`_delete` if they don't already exist under those names.)

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_server_ask.py -k brief_specs -v` (adjust filename to whichever file Step 1's read identified)
Expected: FAIL — 404 or similar.

- [ ] **Step 4: Add routes to `dashboard/server.py`**

In the `do_GET` handler, near the existing `if path.startswith("/api/profile/"):` block (~line 624-626), add before the generic profile-read fallback:

```python
            if path.startswith("/api/profile/") and path.endswith("/brief-specs"):
                slug = path[len("/api/profile/"):-len("/brief-specs")]
                return self._send(200, {"specs": fileops.list_brief_specs(slug)})
            if "/brief-specs/" in path:
                slug, brief_id = path[len("/api/profile/"):].split("/brief-specs/", 1)
                return self._send(200, fileops.get_brief_spec(slug, brief_id))
            if path.startswith("/api/profile/") and path.endswith("/voices"):
                slug = path[len("/api/profile/"):-len("/voices")]
                return self._send(200, {"voices": fileops.list_voices(slug)})
            if "/voices/" in path:
                slug, voice_id = path[len("/api/profile/"):].split("/voices/", 1)
                return self._send(200, fileops.get_voice(slug, voice_id))
```

In the `do_POST` handler (or wherever PUT/DELETE for `/api/profile/` are dispatched — check whether this codebase routes PUT/DELETE through the same method or a separate one before placing these), replace the old brief-spec-only block (lines 651-656):

```python
            if path.startswith("/api/profile/") and path.endswith("/brief-spec"):
                slug = path[len("/api/profile/"):-len("/brief-spec")]
                text = body.get("text")
                if text is None:
                    text = body.get("brief_spec", "")
                return self._send(200, {"ok": True, **fileops.write_brief_spec(slug, text)})
```

with the full CRUD set:

```python
            if path.startswith("/api/profile/") and path.endswith("/brief-specs"):
                slug = path[len("/api/profile/"):-len("/brief-specs")]
                text = body.get("text", "")
                platforms = body.get("platforms", "all")
                return self._send(200, {"ok": True, **fileops.create_brief_spec(slug, text, platforms)})
            if "/brief-specs/" in path and self.command == "PUT":
                slug, brief_id = path[len("/api/profile/"):].split("/brief-specs/", 1)
                text = body.get("text", "")
                platforms = body.get("platforms")
                return self._send(200, {"ok": True, **fileops.write_brief_spec(slug, text, brief_id, platforms)})
            if "/brief-specs/" in path and self.command == "DELETE":
                slug, brief_id = path[len("/api/profile/"):].split("/brief-specs/", 1)
                return self._send(200, fileops.delete_brief_spec(slug, brief_id))
            if path.startswith("/api/profile/") and path.endswith("/voices"):
                slug = path[len("/api/profile/"):-len("/voices")]
                text = body.get("text", "")
                platforms = body.get("platforms", "all")
                return self._send(200, {"ok": True, **fileops.create_voice(slug, text, platforms)})
            if "/voices/" in path and self.command == "PUT":
                slug, voice_id = path[len("/api/profile/"):].split("/voices/", 1)
                text = body.get("text", "")
                platforms = body.get("platforms")
                return self._send(200, {"ok": True, **fileops.update_voice(slug, text, voice_id, platforms)})
            if "/voices/" in path and self.command == "DELETE":
                slug, voice_id = path[len("/api/profile/"):].split("/voices/", 1)
                return self._send(200, fileops.delete_voice(slug, voice_id))
```

Check how this server dispatches PUT/DELETE (`self.command` may not exist on this handler class — confirm the actual mechanism by reading the class definition's `do_PUT`/`do_DELETE` or single dispatch method before finalizing; adjust the `if ... and self.command == "PUT"` guards to match however the file already distinguishes HTTP methods, e.g. separate `do_PUT`/`do_DELETE` methods rather than one shared body).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_server_ask.py -v` (or whichever file)
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/server.py tests/test_server_ask.py
git commit -m "feat: HTTP routes for listing/creating/updating/deleting brief-specs and voices"
```

---

### Task 7: generate.py — brief_id/voice_id-aware generation

**Files:**
- Modify: `generate.py`
- Test: new `tests/test_generate_brief_voice_selection.py`

**Interfaces:**
- Consumes: Task 1's `read_spec_text(profile_dir, brief_id)`, `read_voice_text`/voice cascade files.
- Produces: `build_voice_cascade(profile_dir, platforms=None, voice_id="vc1") -> str`; `do_brief(root, profile_slug, post_id, instruction="", brief_id=None, voice_id=None)`; `do_plan(...)` gains per-brief/per-voice count support when multiple exist; CLI `brief` subcommand gains `--spec`/`--voice`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_generate_brief_voice_selection.py`:

```python
import tempfile, unittest
from pathlib import Path

from generate import build_voice_cascade
from core.voice_util import write_voice_text


class VoiceCascadeSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profiles" / "demo"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_voice_id_used_when_unspecified(self):
        write_voice_text(self.profile_dir, "Default voice text.")
        cascade = build_voice_cascade(self.profile_dir)
        self.assertIn("Default voice text.", cascade)

    def test_explicit_voice_id_selects_that_voice(self):
        write_voice_text(self.profile_dir, "Default voice text.")
        write_voice_text(self.profile_dir, "TikTok voice text.", voice_id="vc2")
        cascade = build_voice_cascade(self.profile_dir, voice_id="vc2")
        self.assertIn("TikTok voice text.", cascade)
        self.assertNotIn("Default voice text.", cascade)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generate_brief_voice_selection.py -v`
Expected: FAIL — `build_voice_cascade` still reads `profile.md`'s body, ignores `voice_id`, `TypeError` on the unexpected kwarg.

- [ ] **Step 3: Update `build_voice_cascade` in `generate.py`**

Add the import near the top of `generate.py` (alongside the existing `from core.brief_spec_util import (...)`):

```python
from core.voice_util import read_voice_text
```

Replace the profile-voice paragraph inside `build_voice_cascade` (lines 232-253, specifically the signature and the `profile_md` block):

```python
def build_voice_cascade(profile_dir: Path, platforms: list = None, voice_id: str = "vc1") -> str:
    """Compose the VOICE CASCADE: project voice + profile voice + channel guidelines.

    project voice    = projects/<slug>/project.md body
    profile voice    = voices/<voice_id>.md body (selection is always explicit —
                        this never auto-picks a voice by platform)
    channel guidelines = channels/<channel-slug>/guidelines.md
                         (one file per channel whose platform matches `platforms`)

    Returns a single string ready to pipe as stdin to claude.
    """
    parts = []

    # project voice (grandparent of profile_dir)
    project_dir = profile_dir.parent.parent  # profiles/<slug> → project/<slug>
    project_md = project_dir / "project.md"
    if project_md.exists():
        parts.append("--- PROJECT VOICE ---\n" + project_md.read_text(encoding="utf-8").strip())

    # profile voice — explicit voice_id, default vc1
    voice_text = read_voice_text(profile_dir, voice_id).strip()
    if voice_text:
        parts.append("--- PROFILE VOICE ---\n" + voice_text)
```

Leave the channel-guidelines loop (the rest of the function) unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate_brief_voice_selection.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `brief_id`/`voice_id` through `do_brief` and its CLI flags**

Update `do_brief`'s signature and the two `read_spec_text`/`build_voice_cascade` calls (lines 410-431):

```python
def do_brief(root: Path, profile_slug: str, post_id: str, instruction: str = "",
             brief_id: str | None = None, voice_id: str | None = None):
    profile_dir = find_profile_dir(root, profile_slug)
    profile_md = profile_dir / "profile.md"
    if not profile_md.exists():
        raise JobError(f"profile.md not found: {profile_md}")
    content_dir = profile_dir / "content"
    slot = find_slot(content_dir, post_id)
    if slot is None:
        raise JobError(f"slot '{post_id}' not found in any plan-*.json under {content_dir}")

    # Explicit flag wins; else whatever this post was minted with; else the default.
    brief_id = brief_id or slot.get("brief_id") or "br1"
    voice_id = voice_id or slot.get("voice_id") or "vc1"

    constraints = json.loads((PROMPTS / "platform-constraints.json").read_text(encoding="utf-8"))
    slot_channels = slot.get("channels") or []
    plat = slot.get("platform") or (slot_channels[0] if slot_channels else None)
    plat_cfg = constraints.get(plat, {}) if plat else {}

    voice_text = build_voice_cascade(profile_dir, [plat] if plat else None, voice_id)

    brief_spec = read_spec_text(profile_dir, brief_id).strip()
```

The rest of `do_brief` is unchanged (it already references the local `brief_spec`/`voice_text` names).

Update the CLI `brief` subcommand (find it in `main()`'s argparse setup, near the other subparsers — search for `sub.add_parser("brief"` or similar) to add `--spec`/`--voice`:

```python
    bp.add_argument("--spec", dest="brief_id", default=None, help="brief-spec id to use, e.g. br2 (default: post's stored id, else br1)")
    bp.add_argument("--voice", dest="voice_id", default=None, help="voice id to use, e.g. vc2 (default: post's stored id, else vc1)")
```

and update the call site that invokes `do_brief(...)` from that subcommand to pass `args.brief_id, args.voice_id` through.

- [ ] **Step 6: Run the full generate.py-related test suite**

Run: `python -m pytest tests/ -k generate -v`
Expected: PASS.

- [ ] **Step 7: `do_plan` — per-brief/per-voice count support**

Update `do_plan`'s signature to accept optional split dicts, defaulting to today's single-cadence behavior when a profile has only one brief/voice:

```python
def do_plan(root: Path, profile_slug: str, period: str, platforms, cadence, focus,
            brief_counts: dict | None = None, voice_counts: dict | None = None):
```

Inside `do_plan`, after computing `brief_spec = read_spec_text(profile_dir).strip()` (line 352), branch on whether more than one brief-spec/voice exists:

```python
    from core.brief_spec_util import list_brief_ids
    from core.voice_util import list_voice_ids
    brief_ids = list_brief_ids(profile_dir)
    voice_ids = list_voice_ids(profile_dir)
```

Add to the `--- PARAMETERS ---` block (after the existing `cadence` line, ~line 360) only when there's more than one to choose from:

```python
    if len(brief_ids) > 1:
        counts = brief_counts or {brief_ids[0]: cadence * len(platforms)}
        params += "\n--- BRIEF-SPEC SPLIT (mint this many posts per brief id) ---\n"
        params += "\n".join(f"{bid}: {n}" for bid, n in counts.items()) + "\n"
    if len(voice_ids) > 1:
        counts = voice_counts or {voice_ids[0]: cadence * len(platforms)}
        params += "\n--- VOICE SPLIT (mint this many posts per voice id) ---\n"
        params += "\n".join(f"{vid}: {n}" for vid, n in counts.items()) + "\n"
```

After minting ids for the freshly generated posts (the existing `mint_post_ids` block, ~line 386-389), stamp each post with its `brief_id`/`voice_id` — when a split was requested, assign in order; otherwise everyone gets the single existing id:

```python
    def _assign_ids(counts, default_id):
        if not counts:
            return [default_id] * len(obj.get("posts", []))
        out = []
        for bid, n in counts.items():
            out.extend([bid] * n)
        while len(out) < len(obj.get("posts", [])):
            out.append(default_id)
        return out[:len(obj.get("posts", []))]

    assigned_briefs = _assign_ids(brief_counts, brief_ids[0])
    assigned_voices = _assign_ids(voice_counts, voice_ids[0])
    for post, bid, vid in zip(obj.get("posts", []), assigned_briefs, assigned_voices):
        post["brief_id"] = bid
        post["voice_id"] = vid
```

- [ ] **Step 8: Write failing test for the split assignment, then make it pass**

`tests/test_generate_plan.py` already has the right fixture (a `demo` profile under a temp root, `generate.run_job` monkeypatched) — add the split test there rather than duplicating the setup:

```python
    def test_brief_and_voice_counts_split_across_minted_posts(self):
        write(self.root / "projects/acme/profiles/demo/brief-specs/br1.md", "---\nplatforms: all\n---\nDefault.")
        write(self.root / "projects/acme/profiles/demo/brief-specs/br2.md", "---\nplatforms: tiktok\n---\nTikTok only.")
        write(self.root / "projects/acme/profiles/demo/voices/vc1.md", "---\nplatforms: all\n---\nDefault voice.")
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [
                {"id": f"draft-{i:03d}", "date": "2026-07-01", "pillar": "curiosity",
                 "channels": ["demo-tiktok"], "working_title": f"T{i}", "concept": "C"}
                for i in range(5)
            ],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None,
                          brief_counts={"br1": 3, "br2": 2})
        posts = self._plan_file()["posts"]
        self.assertEqual([p["brief_id"] for p in posts], ["br1", "br1", "br1", "br2", "br2"])
        self.assertEqual([p["voice_id"] for p in posts], ["vc1"] * 5)  # only one voice exists — no split needed

    def test_no_split_requested_uses_first_brief_and_voice_for_everyone(self):
        write(self.root / "projects/acme/profiles/demo/brief-specs/br2.md", "---\nplatforms: tiktok\n---\nSecond.")
        generate.run_job = lambda *a, **k: {
            "period": "p", "profile": "demo",
            "posts": [{"id": "draft-001", "date": "2026-07-01", "pillar": "curiosity",
                       "channels": ["demo-tiktok"], "working_title": "T", "concept": "C"}],
        }
        generate.do_plan(self.root, "demo", "2026-07-01 to 2026-07-14", ["tiktok"], 3, None)
        post = self._plan_file()["posts"][0]
        self.assertEqual(post["brief_id"], "br1")
        self.assertEqual(post["voice_id"], "vc1")
```

Run: `python -m pytest tests/test_generate_plan.py -v`
Expected: FAIL first (no `brief_id`/`voice_id` on minted posts, `do_plan` doesn't accept `brief_counts` kwarg yet), then PASS once Step 7's `do_plan` changes land.

- [ ] **Step 9: Update the `plan` CLI subcommand for optional per-brief/per-voice flags**

Near the existing `pp.add_argument("--cadence", ...)` (line 569), add:

```python
    pp.add_argument("--brief-counts", default="", help='e.g. "br1:5,br2:2" — omit to use one brief for everything')
    pp.add_argument("--voice-counts", default="", help='e.g. "vc1:5,vc2:2" — omit to use one voice for everything')
```

Add a small parse helper near the top of `generate.py` (with the other helpers):

```python
def _parse_counts(raw: str) -> dict | None:
    if not raw.strip():
        return None
    out = {}
    for part in raw.split(","):
        k, _, v = part.partition(":")
        if k.strip() and v.strip().isdigit():
            out[k.strip()] = int(v.strip())
    return out or None
```

Update the `do_plan(...)` call site in `main()` (line ~592) to pass the parsed dicts through:

```python
            do_plan(root, args.profile, args.period, platforms, args.cadence, args.focus,
                    _parse_counts(args.brief_counts), _parse_counts(args.voice_counts))
```

- [ ] **Step 10: Run the full test suite touching generate.py**

Run: `python -m pytest tests/ -k "generate or plan or brief" -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add generate.py tests/test_generate_brief_voice_selection.py tests/test_generate_plan.py
git commit -m "feat: generate.py resolves brief/voice by explicit id, supports per-id post-count split"
```

---

### Task 8: Dashboard Profile Setup UI — repeatable brief/voice rows

**Files:**
- Modify: `dashboard/app.js`, `dashboard/os-ids.js`

**Interfaces:**
- Consumes: Task 6's `/api/profile/<slug>/brief-specs` and `/api/profile/<slug>/voices` endpoints.
- Produces: updated `renderProfileSetup` rendering N rows instead of 1 textarea each, with add/delete buttons and a platform-tag `<select>` per row built from that profile's channel platforms.

- [ ] **Step 1: Update `dashboard/os-ids.js` lookup helpers**

Change (lines 64-65):

```javascript
  profBriefSpec(profile) { return this.get(`brief-spec:prof:${profile}`); },
  profVoice(profile) { return this.get(`voice:prof:${profile}`); },
```

to:

```javascript
  profBriefSpec(profile, id="br1") { return this.get(`brief-spec:prof:${profile}:${id}`); },
  profVoice(profile, id="vc1") { return this.get(`voice:prof:${profile}:${id}`); },
```

- [ ] **Step 2: Replace `renderProfileSetup` (lines 1228-1268) in `dashboard/app.js`**

```javascript
async function renderProfileSetup(slug){
  CURRENT_PROFILE_SLUG = slug;
  const [profData, specsRes, voicesRes] = await Promise.all([
    api(`/api/profile/${slug}`),
    api(`/api/profile/${slug}/brief-specs`),
    api(`/api/profile/${slug}/voices`),
    ensureIdRegistry(),
  ]);
  const profName = profData.name||slug;
  const setupTabId = composedIdOnly(OSID.tabProf(slug, "setup"));
  const platforms = await api(`/api/profile/${slug}/platforms`).catch(()=>({platforms:[]}));
  const platformOpts = ["all", ...(platforms.platforms||[])];

  function row(kind, item){ // kind: "voice" | "brief"
    const idAttr = item.id;
    const composedId = kind==="voice" ? composedIdOnly(OSID.profVoice(slug, item.id)) : composedIdOnly(OSID.profBriefSpec(slug, item.id));
    const opts = platformOpts.map(p=>`<option value="${esc(p)}" ${item.platforms===p?"selected":""}>${esc(p)}</option>`).join("");
    return `<div class="setup-row" data-kind="${kind}" data-id="${esc(idAttr)}" style="margin-bottom:14px;border:1px solid var(--hair);border-radius:12px;padding:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        ${flabel(idAttr, composedId)}
        <div>
          <select class="setup-platform" style="font:inherit;border:1px solid var(--hair);border-radius:8px;padding:4px 8px">${opts}</select>
          <button class="btn danger-btn setup-delete" style="margin-left:6px">Delete</button>
        </div>
      </div>
      <textarea class="setup-text" style="width:100%;min-height:160px;border:1px solid var(--hair);border-radius:10px;padding:12px 14px;font:13.5px/1.7 var(--body);background:rgba(255,255,255,.82);resize:vertical">${esc(item.text||"")}</textarea>
    </div>`;
  }

  $("#main").innerHTML = `${pageHeader("Profile setup", profName, `<button class="btn danger-btn" id="delProfBtn" style="color:#c0392b">Delete profile</button><button class="btn primary" id="saveProfBtn">Save</button>`, setupTabId || OSID.prof(slug))}
    <div class="scroll">
      <div style="max-width:740px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px">
          <div>
            ${flabel("Display name")}
            <input id="ps-name" value="${esc(profName)}" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
          <div>
            ${flabel("Topic / niche")}
            <input id="ps-topic" value="${esc(profData.topic||"")}" placeholder="e.g. Film reviews for movie lovers" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin:0 0 6px">
          <div>${flabel("Brand voice & tone")}</div>
          <button class="btn" id="addVoiceBtn">+ Add voice</button>
        </div>
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">Describe how this brand speaks. Add a second voice if you want a distinct one for specific platforms — nothing auto-switches between them, you pick which to use each time you generate.</p>
        <div id="voiceRows">${voicesRes.voices.map(v=>row("voice", v)).join("")}</div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin:26px 0 6px">
          <div>${flabel("Post brief spec")}</div>
          <button class="btn" id="addBriefBtn">+ Add brief-spec</button>
        </div>
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">Per-profile output rules for new posts. Changing one does not alter briefs already written. Add a second one if you want separate rules for a platform — selection is always manual.</p>
        <div id="briefRows">${specsRes.specs.map(s=>row("brief", s)).join("")}</div>
      </div>
    </div>`;
  wireIdChips($("#main"));

  $("#addVoiceBtn").onclick = async()=>{
    await jpost(`/api/profile/${slug}/voices`, {text:"", platforms:"all"});
    renderProfileSetup(slug);
  };
  $("#addBriefBtn").onclick = async()=>{
    await jpost(`/api/profile/${slug}/brief-specs`, {text:"", platforms:"all"});
    renderProfileSetup(slug);
  };
  $$(".setup-delete").forEach(btn=>{
    btn.onclick = async()=>{
      const rowEl = btn.closest(".setup-row");
      const kind = rowEl.dataset.kind, id = rowEl.dataset.id;
      const path = kind==="voice" ? `voices/${id}` : `brief-specs/${id}`;
      try{ await api(`/api/profile/${slug}/${path}`, {method:"DELETE"}); renderProfileSetup(slug); }
      catch(e){ toast("✗ "+e.message); }
    };
  });

  $("#saveProfBtn").onclick = async()=>{
    const profile={name:$("#ps-name").value, topic:$("#ps-topic").value};
    try{
      await jpost(`/api/profile/${slug}/update`, profile);
      for(const rowEl of $$(".setup-row")){
        const kind = rowEl.dataset.kind, id = rowEl.dataset.id;
        const text = rowEl.querySelector(".setup-text").value;
        const plat = rowEl.querySelector(".setup-platform").value;
        const path = kind==="voice" ? `voices/${id}` : `brief-specs/${id}`;
        await api(`/api/profile/${slug}/${path}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text, platforms:plat})});
      }
      toast("Saved ✓"); renderRail();
    }
    catch(e){ toast("✗ "+e.message); }
  };
  $("#delProfBtn").onclick = ()=>navigate(`#/profile/${slug}/delete`);
}
```

Check whether `$$` (query-all helper) already exists elsewhere in `app.js` — grep for `function \$\$` or similar before assuming it does; if it doesn't exist, add:

```javascript
function $$(sel){ return Array.from(document.querySelectorAll(sel)); }
```

near the existing `function $(sel)` definition.

- [ ] **Step 3: Add the `/api/profile/<slug>/platforms` read route**

In `dashboard/server.py`'s GET dispatch, add near the other `/api/profile/` branches:

```python
            if path.startswith("/api/profile/") and path.endswith("/platforms"):
                slug = path[len("/api/profile/"):-len("/platforms")]
                return self._send(200, {"platforms": fileops.profile_platforms(slug)})
```

- [ ] **Step 4: Manual verification (UI has no automated test harness in this repo — confirm via the dashboard itself)**

Run: start the dashboard server per this project's usual dev command (check `CLAUDE.md`/README for the exact command — likely `python dashboard/server.py` or similar), open a profile's Setup page in a browser, and confirm: existing voice/brief-spec still show (migrated content), "+ Add voice" / "+ Add brief-spec" create a new row with a platform dropdown, Save persists all rows, Delete removes a row (but is rejected via toast when it's the last one).

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js dashboard/os-ids.js dashboard/server.py
git commit -m "feat: Profile Setup UI supports multiple brief-specs and voices with platform tags"
```

---

### Task 9: Update AI-facing docs (ai_rules.py / CLAUDE.md sync)

**Files:**
- Modify: `dashboard/ai_rules.py`
- Test: `tests/test_brief_spec_sync.py` (existing — verifies CLAUDE.md stays in sync with ai_rules.py constants; read it to learn the exact sync mechanism before editing)

**Interfaces:**
- Consumes: nothing.
- Produces: updated `BRIEF_SPEC`, `WRITES_TABLE`, `MUTATION_CMDS` constants reflecting the new command surface.

- [ ] **Step 1: Read `tests/test_brief_spec_sync.py` to learn the sync mechanism**

Confirm whether CLAUDE.md is generated from `ai_rules.py` by a script (run manually) or whether the test only checks textual consistency between the two files. This determines whether Step 3 needs to also hand-edit `CLAUDE.md` or run a generator command.

- [ ] **Step 2: Update `dashboard/ai_rules.py`**

Replace `BRIEF_SPEC` (lines 76-80):

```python
BRIEF_SPEC = """## Brief spec & voice (a profile can have several of each)
Brief-spec path: `projects/<project>/profiles/<profile>/brief-specs/br{N}.md`. Voice path: `.../voices/vc{N}.md`. Each file has a `platforms:` tag (`all` or a comma list from that profile's channels) — informational only, selection between multiple is always manual, never auto-matched.
- Read one: `get-brief-spec --profile <slug> [--id br2]` / `get-voice --profile <slug> [--id vc2]`. List all: add `--list`.
- Edit existing: `update-brief-spec --profile <slug> [--id br2] [--platforms ...] --text "..."` / `update-voice` same shape. Defaults to br1/vc1 when `--id` omitted.
- Add a new one: `create-brief-spec --profile <slug> [--platforms ...] --text "..."` / `create-voice` same shape — mints the next id.
- Delete: `delete-brief-spec --profile <slug> --id br2` / `delete-voice` — rejected if it's the only one left.
New posts only; existing briefs grandfathered."""

VOICE_SELECTION = """## Which brief/voice to use when generating
Default is br1/vc1. If a profile has more than one, say which to use explicitly: `generate-brief --id <post-id> --spec br2 --voice vc2`, or in chat "generate this post's brief using br2". A post remembers which pair produced it (`brief_id`/`voice_id`) and reuses that pair on regenerate unless told otherwise. `generate-plan` will ask for a count per brief/voice when a profile has more than one of either."""
```

Update `WRITES_TABLE` (lines 41-42) — replace the `Profile voice/name/topic` and `Brief spec` rows:

```
| Profile name/topic | `update-profile --slug <slug> [--name] [--topic]` |
| Brief spec (one of several) | `create-brief-spec` / `update-brief-spec --profile <slug> [--id br2] [--platforms ...] --text "..."` |
| Voice (one of several) | `create-voice` / `update-voice --profile <slug> [--id vc2] [--platforms ...] --text "..."` |
```

Update the "Banned" line (line 48) to also cover the new dirs:

```
Banned: direct file writes, `set-brief`, `patch-brief`, editing `briefs/*.json`, `brief-specs/*.md`, or `voices/*.md` by hand."""
```

Update `MUTATION_CMDS` (lines 87-95) to add the new command names:

```python
MUTATION_CMDS = (
    "create-project, create-profile, create-channel, create-intake, create-technical, create-memo, "
    "create-experiment, update-experiment, create-product, add-feature, update-roadmap, "
    "update-intake, update-technical, get-subsections, update-subsections, add-subsection, "
    "update-validation-tab, "
    "add-slide, add-post, create-activity, create-milestone, mark-done, update-post, set-status, "
    "update-project, update-profile, update-channel, update-milestone, update-brief, generate-brief, "
    "generate-plan, revise-post, update-brief-spec, create-brief-spec, delete-brief-spec, "
    "create-voice, update-voice, delete-voice"
)
```

Add `VOICE_SELECTION` to wherever `BRIEF_SPEC`/`POST_BRIEFS` are assembled into `CHAT_RAIL`/`TERMINAL_RULES` (find the f-string that currently interpolates `{BRIEF_SPEC}` and `{POST_BRIEFS}` and add `{VOICE_SELECTION}` alongside them).

- [ ] **Step 3: Run the sync test**

Run: `python -m pytest tests/test_brief_spec_sync.py -v`
Expected: PASS if the mechanism is textual-consistency-only; if it's a generator, run whatever regenerates `CLAUDE.md` per Step 1's findings, then re-run this test.

- [ ] **Step 4: Commit**

```bash
git add dashboard/ai_rules.py CLAUDE.md
git commit -m "docs: update chat/terminal rules for multiple brief-specs and voices per profile"
```

---

### Task 10: End-to-end migration verification + full suite

**Files:**
- Test: new `tests/test_brief_voice_migration.py`, then full suite

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write an end-to-end migration test**

```python
import tempfile, unittest
from pathlib import Path
import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db
from core.ids import build_id_registry


class MigrationEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\ntopic: film\nproject: acme\n---\nLegacy voice.\n")
        write(prof / "brief-spec.md", "Legacy brief rules.")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_profile_reads_correctly_pre_and_post_migration(self):
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Legacy brief rules.")
        self.assertEqual(fileops.list_voices("demo")[0]["text"].strip(), "Legacy voice.")
        # legacy files gone, new structure present
        prof_dir = fileops.ROOT / "projects" / "acme" / "profiles" / "demo"
        self.assertFalse((prof_dir / "brief-spec.md").exists())
        self.assertTrue((prof_dir / "brief-specs" / "br1.md").is_file())
        self.assertTrue((prof_dir / "voices" / "vc1.md").is_file())
        # idempotent re-read
        self.assertEqual(fileops.get_brief_spec("demo")["text"].strip(), "Legacy brief rules.")

    def test_adding_second_brief_and_regenerating_ids_is_stable(self):
        fileops.create_brief_spec("demo", "Second.", platforms="all")
        self.assertEqual(fileops.list_brief_specs("demo")[1]["id"], "br2")
        fileops.delete_brief_spec("demo", "br2")
        fileops.create_brief_spec("demo", "Third.", platforms="all")
        self.assertEqual(fileops.list_brief_specs("demo")[1]["id"], "br3")  # never reuses br2
```

- [ ] **Step 2: Run test to verify it passes (this task should require no new production code if Tasks 1-9 are correct — it's a regression check)**

Run: `python -m pytest tests/test_brief_voice_migration.py -v`
Expected: PASS. If it fails, the failure points at exactly which earlier task's contract was violated — fix there, not by special-casing this test.

- [ ] **Step 3: Run the entire test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS, zero failures, zero errors.

- [ ] **Step 4: Run the public-repo usage-data guard (mandatory per CLAUDE.md before any commit in this repo)**

Run: `python -m pytest tests/test_no_usage_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_brief_voice_migration.py
git commit -m "test: end-to-end migration and id-stability coverage for multi-brief/voice"
```

---

## Post-implementation note

Existing profiles' `brief-spec.md` / `profile.md` body migrate lazily on first touch (first read or write through any of the new fileops functions) — no separate migration script or command is needed; simply exercising the dashboard or osctl against a profile is enough to trigger it.
