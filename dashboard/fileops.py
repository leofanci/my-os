"""fileops.py — WRITE side of the dashboard API.

The dashboard NEVER writes os.db. It mutates the authored source FILE (the plan
JSON / brief JSON), then re-runs index.py so the derived index catches up. This
module is that isolated mutation layer — the server-shaped seam that keeps a
future server migration mechanical.

Pipeline status state machine (lives in the plan file's post object, mirrored to
posts.status on re-index):
    planned -> approved_slot -> briefed -> approved -> published
    (rejected at any review point; rejected can reopen to planned)

Content lives under:
    projects/<project-slug>/profiles/<profile-slug>/
        profile.md
        content/plan-*.json      # posts: {id, status, date?, pillar?, working_title?, channels:[...]}
        content/briefs/<post-id>.json
        channels/<channel-slug>/channel.md
        channels/<channel-slug>/guidelines.md
"""

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from core.brief_spec_util import (
    allowed_brief_keys,
    delete_brief,
    list_brief_ids,
    merge_fields_from_slot,
    next_brief_id,
    normalize_brief_for_spec,
    read_spec_platforms,
    read_spec_text,
    validate_brief_obj,
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
from core.ids import (
    build_id_registry,
    find_duplicate_post_ids,
    lk_experiment,
    lk_feature,
    lk_fld_brief,
    lk_memo,
    lk_prod,
    mint_post_ids,
    next_activity_id,
    next_experiment_stem,
    next_memo_version,
    next_milestone_id,
    slug_key,
)
from core.project_schemas import (
    FEATURE_PRIORITIES,
    MEMO_TYPES,
    ROADMAP_SECTION_ALIASES,
    dumps_json,
    normalize_experiment_body,
    normalize_markdown,
    normalize_memo_body,
    parse_markdown_sections,
)
from core.subsections import (
    DOC_META,
    add_doc_subsection,
    ensure_config,
    load_config,
    normalize_doc_text,
    parse_subsections_arg as _parse_subsections_arg,
    save_config,
    set_doc_subsections,
    set_validation_tab_subsections,
    starter_text,
    subsections_api_payload,
    subsections_for_doc,
    validation_tab_subsections,
)


def parse_subsections_arg(raw: str) -> list[str]:
    return _parse_subsections_arg(raw)

ROOT = Path(__file__).resolve().parent.parent


def _composed_id(lookup_key: str) -> str:
    """Map internal lookup key → composed id after reindex."""
    from dashboard import db  # noqa: WPS433 — avoid import cycle at module load
    reg = build_id_registry(db.tree(), db.posts(), root=ROOT)
    return reg.get(lookup_key) or lookup_key

# index.py is a fixed script (it lives at the repo root); ROOT is the WORKSPACE
# it indexes. They coincide in production but tests point ROOT at a temp dir.
_INDEX_SCRIPT = Path(__file__).resolve().parent.parent / "index.py"

ALLOWED_TRANSITIONS = {
    "planned":       {"approved_slot", "rejected"},
    "approved_slot": {"briefed", "rejected", "planned"},
    "briefed":       {"approved", "rejected", "approved_slot"},
    "approved":      {"published", "rejected"},
    "published":     set(),
    "rejected":      {"planned"},
}


class ActionError(Exception):
    """A rejected dashboard action (bad transition, missing post, job failure)."""


# --------------------------------------------------------------------------- #
def reindex():
    res = subprocess.run(
        [sys.executable, str(_INDEX_SCRIPT), str(ROOT)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise ActionError(f"re-index failed: {res.stderr.strip()[:600]}")
    # Guard: the SQLite index upserts by id, so two posts sharing one id
    # silently collapse to whichever plan file was read last — invisible
    # from the index itself. Check the raw plan files on every reindex so a
    # collision (batch job, hand-edit, drifted counter) fails loudly right
    # where it was introduced instead of surfacing later as a post that
    # resolves to the wrong content.
    dupes = find_duplicate_post_ids(ROOT)
    if dupes:
        detail = "; ".join(f"'{pid}' in {', '.join(files)}" for pid, files in sorted(dupes.items()))
        raise ActionError(f"duplicate post id(s) found after reindex: {detail}")
    return res.stdout


def _profile_dir(slug):
    """Find the profile directory for the given slug under any project."""
    for candidate in ROOT.glob(f"projects/*/profiles/{slug}"):
        if candidate.is_dir():
            return candidate
    raise ActionError(f"profile '{slug}' not found")


def _channel_dir(slug):
    """Find the channel directory for the given slug under any profile."""
    for candidate in ROOT.glob(f"projects/*/profiles/*/channels/{slug}"):
        if candidate.is_dir():
            return candidate
    raise ActionError(f"channel '{slug}' not found")


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


def _parse_channels(raw):
    """Parse a comma/space-separated channel slug string into a list of slugs."""
    if not raw:
        return []
    slugs = [s.strip() for s in re.split(r"[,\s]+", raw.strip()) if s.strip()]
    return slugs


def _post_profile_hint(post_id: str, profile_slug: str | None = None) -> str | None:
    """Resolve which profile owns a post id — explicit hint or os.db index."""
    if profile_slug and str(profile_slug).strip():
        return str(profile_slug).strip()
    try:
        import dashboard.db as db

        rows = db._rows("SELECT profile_slug FROM posts WHERE id = ?", (post_id,))
        if rows:
            return rows[0]["profile_slug"]
    except Exception:
        pass
    return None


def find_post(post_id, profile_slug=None):
    """Locate the plan file + post object for a post id. Returns a dict context.

    Post ids must be unique workspace-wide, but when duplicates exist (e.g. post-001
    in both profile-a and profile-b) the os.db profile_slug disambiguates.
    Callers that know the profile (dashboard post views) should pass profile_slug.
    """
    post_id = str(post_id or "").strip()
    if not post_id:
        raise ActionError("post id is required")
    hint = _post_profile_hint(post_id, profile_slug)
    plan_glob = (
        ROOT.glob(f"projects/*/profiles/{hint}/content/plan-*.json")
        if hint
        else ROOT.glob("projects/*/profiles/*/content/plan-*.json")
    )
    matches = []
    for plan in sorted(plan_glob):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for post in data.get("posts", []) if isinstance(data, dict) else []:
            if post.get("id") == post_id:
                matches.append({
                    "plan": plan,
                    "data": data,
                    "post": post,
                    "profile_slug": plan.parent.parent.name,
                })
    if not matches:
        raise ActionError(f"post '{post_id}' not found in any plan file")
    if len(matches) == 1:
        return matches[0]
    resolved = _post_profile_hint(post_id)
    if resolved:
        for ctx in matches:
            if ctx["profile_slug"] == resolved:
                return ctx
    names = ", ".join(sorted({m["profile_slug"] for m in matches}))
    raise ActionError(
        f"post '{post_id}' exists in multiple profiles ({names}) — pass profile to disambiguate"
    )


def _write_plan(ctx):
    ctx["plan"].write_text(
        json.dumps(ctx["data"], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _effective_status(ctx):
    """The post's real status, reconciled with reality on disk.

    A brief written directly via `generate.py brief` (batch jobs, the terminal)
    creates the brief file but does NOT advance the plan-file status — only
    generate_brief() does. The indexer already *displays* such posts as 'briefed';
    mirror that here so a transition off the UI's "Review →" button doesn't fail
    with an illegal-transition error. Persists the correction when it applies.
    """
    current = ctx["post"].get("status") or "planned"
    brief_file = ctx["plan"].parent / "briefs" / f"{ctx['post'].get('id')}.json"
    if brief_file.exists() and current in ("planned", "approved_slot"):
        ctx["post"]["status"] = current = "briefed"
        _write_plan(ctx)
    return current


def set_status(post_id, new_status, profile_slug=None):
    """Transition a post's status in its plan file, then re-index."""
    if new_status not in ALLOWED_TRANSITIONS:
        raise ActionError(f"unknown status '{new_status}'")
    ctx = find_post(post_id, profile_slug)
    current = _effective_status(ctx)
    if new_status == current:
        raise ActionError(f"post is already '{current}'")
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ActionError(
            f"illegal transition {current} -> {new_status}"
            f" (allowed: {sorted(ALLOWED_TRANSITIONS.get(current, set())) or 'none'})"
        )
    ctx["post"]["status"] = new_status
    _write_plan(ctx)
    reindex()
    return {"id": post_id, "status": new_status, "from": current}


def generate_brief(post_id, instruction=None, profile_slug=None, brief_id=None, voice_id=None):
    """Run the claude -p brief job (Write button). Persists via write_brief inside generate.py.

    brief_id/voice_id override which brief-spec/voice to use — omit to use
    whatever the post is stored with, else br1/vc1 (see generate.py do_brief)."""
    ctx = find_post(post_id, profile_slug)
    current = ctx["post"].get("status") or "planned"
    if current not in ("planned", "approved_slot"):
        raise ActionError(f"can only brief a planned/approved_slot post (is '{current}')")

    cmd = [sys.executable, str(ROOT / "generate.py"),
           "--workspace", str(ROOT), "brief", ctx["profile_slug"], post_id]
    if instruction and instruction.strip():
        cmd += ["--instruction", instruction.strip()]
    if brief_id:
        cmd += ["--spec", brief_id]
    if voice_id:
        cmd += ["--voice", voice_id]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ActionError(f"brief job failed: {(res.stderr or res.stdout).strip()[:800]}")
    return {"id": post_id, "status": "briefed", "stdout": res.stdout.strip()}


def update_brief(post_id, instruction=None, profile_slug=None, brief_id=None, voice_id=None):
    """Natural-language brief create or update — primary chat path.

    Existing brief → revise job with the user's words. No brief yet → generate
    job (optional direction). Same validated persist path either way."""
    ctx = find_post(post_id, profile_slug)
    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if brief_file.exists():
        if not (instruction or "").strip():
            raise ActionError("instruction is required to change an existing brief")
        return revise_post(post_id, instruction, profile_slug, brief_id, voice_id)
    return generate_brief(post_id, instruction, profile_slug, brief_id, voice_id)


def revise_post(post_id, instruction, profile_slug=None, brief_id=None, voice_id=None):
    """Revise a slot (idea) or brief (draft) in place via the AI revise job.

    For drafts the brief file is overwritten and the plan-file version is bumped.
    For ideas the slot fields are updated directly in the plan file.
    brief_id/voice_id override which brief-spec/voice to use — omit to use
    whatever the post is stored with, else br1/vc1 (see generate.py do_revise)."""
    if not instruction or not instruction.strip():
        raise ActionError("instruction is required")
    ctx = find_post(post_id, profile_slug)
    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    is_draft = brief_file.exists()

    cmd = [sys.executable, str(ROOT / "generate.py"),
           "--workspace", str(ROOT), "revise", ctx["profile_slug"], post_id,
           "--instruction", instruction]
    if brief_id:
        cmd += ["--spec", brief_id]
    if voice_id:
        cmd += ["--voice", voice_id]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ActionError(f"revise job failed: {(res.stderr or res.stdout).strip()[:800]}")

    if is_draft:
        ctx = find_post(post_id, profile_slug)
        ctx["post"]["version"] = int(ctx["post"].get("version") or 1) + 1
        _write_plan(ctx)

    reindex()
    return {"id": post_id, "is_draft": is_draft, "stdout": res.stdout.strip()}


def _parse_frontmatter(text):
    """Return (dict of frontmatter fields, body string) for --- ... --- text."""
    fm, body = {}, ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            body = parts[2].strip()
    return fm, body


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


def read_channel_guidelines(slug):
    """Read guidelines for a channel from its guidelines.md file."""
    f = _channel_dir(slug) / "guidelines.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def write_channel_guidelines(slug, text):
    """Save a channel's guidelines (authored file; not indexed, so no re-index)."""
    (_channel_dir(slug) / "guidelines.md").write_text(text or "", encoding="utf-8")
    return {"slug": slug, "chars": len(text or "")}


def refine_guidelines(slug, raw_text):
    """AI-polish rough guideline notes via generate.py; returns text, does NOT save."""
    _channel_dir(slug)
    res = subprocess.run(
        [sys.executable, str(ROOT / "generate.py"),
         "--workspace", str(ROOT), "refine-guidelines", slug],
        input=raw_text or "", capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise ActionError(f"refine failed: {(res.stderr or res.stdout).strip()[:800]}")
    return {"refined": res.stdout}


def read_detail(post_id, profile_slug=None):
    """Authored detail for a post: the plan slot + the brief JSON if it exists.

    Prose/authored content is read from FILES (their source of truth), while the
    coordination fields come from os.db via db.py.
    """
    ctx = find_post(post_id, profile_slug)
    brief = None
    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if brief_file.exists():
        try:
            brief = json.loads(brief_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            brief = {"_error": "brief file is not valid JSON"}
    return {"slot": ctx["post"], "brief": brief, "profile_slug": ctx["profile_slug"]}


_POST_FIELDS = ("date", "pillar", "working_title", "concept", "format", "objective", "platform",
                "brief_id", "voice_id")


def add_post(profile_slug, fields):
    """Create a manual idea-slot in the profile's newest plan file (or plan-manual.json)."""
    profile_dir = _profile_dir(profile_slug)
    content = profile_dir / "content"
    content.mkdir(parents=True, exist_ok=True)
    plans = sorted(content.glob("plan-*.json"))
    if plans:
        plan = plans[-1]
        data = json.loads(plan.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("posts"), list):
            raise ActionError(f"plan file {plan.name} has an unexpected shape")
    else:
        plan = content / "plan-manual.json"
        data = {"posts": []}
    project_slug = profile_dir.parent.parent.name
    pid = mint_post_ids(ROOT, project_slug, profile_slug, 1)[0]
    post = {"id": pid, "status": "planned"}
    for k in _POST_FIELDS:
        v = (fields.get(k) or "").strip()
        if v:
            post[k] = v
    channels = _parse_channels(fields.get("channels"))
    if channels:
        post["channels"] = channels
    post.setdefault("brief_id", "br1")
    post.setdefault("voice_id", "vc1")
    data["posts"].append(post)
    plan.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": pid, "profile_slug": profile_slug}


def _merge_brief_patch(existing: dict, patch: dict) -> dict:
    merged = dict(existing)
    for k, v in patch.items():
        if k == "id":
            continue
        if v is None or v == "" or (isinstance(v, list) and not v):
            merged.pop(k, None)
        else:
            merged[k] = v
    return merged


def _sync_slot_identity_to_brief(brief: dict, slot: dict) -> None:
    """Keep brief identity fields aligned with the plan slot after manual edits."""
    for k in ("format", "objective", "pillar", "platform"):
        if slot.get(k):
            brief[k] = slot[k]
    if slot.get("channels"):
        brief["channels"] = slot["channels"]


def update_post(post_id, fields, profile_slug=None):
    """Edit plan-slot fields and, when a brief exists, patch brief JSON in one save."""
    ctx = find_post(post_id, profile_slug)
    for k in _POST_FIELDS:
        if k in fields:
            v = (fields.get(k) or "").strip()
            if v:
                ctx["post"][k] = v
            else:
                ctx["post"].pop(k, None)
    if "channels" in fields:
        channels = _parse_channels(fields.get("channels"))
        if channels:
            ctx["post"]["channels"] = channels
        else:
            ctx["post"].pop("channels", None)
    brief_patch = fields.get("brief")
    if brief_patch is not None:
        if not isinstance(brief_patch, dict):
            raise ActionError("brief must be a JSON object")
        brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
        if not brief_file.exists():
            raise ActionError(f"no brief for post '{post_id}' — generate draft first")
        try:
            existing = json.loads(brief_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ActionError(f"brief file unreadable: {exc}") from exc
        if not isinstance(existing, dict):
            raise ActionError("brief must be a JSON object")
        merged = _merge_brief_patch(existing, brief_patch)
        _sync_slot_identity_to_brief(merged, ctx["post"])
        _write_plan(ctx)
        write_brief(
            post_id, merged, strict_spec=False, set_status=False,
            bump_version_if_exists=True, profile_slug=profile_slug,
        )
    else:
        _write_plan(ctx)
        reindex()
    return {"id": post_id}



def write_brief(post_id, brief, *, bump_version_if_exists=True, set_status=True,
                strict_spec=None, profile_slug=None):
    """Canonical brief persist — write JSON, update plan.

    New briefs validate against current brief-spec.md. Existing briefs are
    grandfathered when the spec changes — they keep their old shape unless
    the user explicitly revises them."""
    if not isinstance(brief, dict):
        raise ActionError("brief must be a JSON object")
    ctx = find_post(post_id, profile_slug)
    slot = ctx["post"]
    briefs_dir = ctx["plan"].parent / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    brief_file = briefs_dir / f"{post_id}.json"
    is_rebrief = brief_file.exists()
    if strict_spec is None:
        strict_spec = not is_rebrief
    spec_text = read_brief_spec(ctx["profile_slug"], slot.get("brief_id") or "br1")
    normalize_brief_for_spec(brief, spec_text)
    for k in merge_fields_from_slot(spec_text):
        if not brief.get(k) and slot.get(k):
            brief[k] = slot[k]
    allowed = allowed_brief_keys(spec_text)
    if allowed is not None:
        for k in list(brief.keys()):
            if k not in allowed:
                del brief[k]
    errs = validate_brief_obj(brief, post_id, spec_text, slot, strict_spec=strict_spec)
    if errs:
        label = "brief does not match profile brief spec" if strict_spec else "brief invalid"
        raise ActionError(f"{label}: " + "; ".join(errs))
    brief["id"] = post_id
    brief_file.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    if set_status:
        ctx["post"]["status"] = "briefed"
    if is_rebrief and bump_version_if_exists:
        ctx["post"]["version"] = int(ctx["post"].get("version") or 1) + 1
    _write_plan(ctx)
    reindex()
    return {"id": post_id, "status": ctx["post"].get("status", "briefed"), "rebrief": is_rebrief}


def set_brief(post_id, brief):
    """Internal persist — generate.py and tests only. Agents use update_brief()."""
    return write_brief(post_id, brief)

def add_slide_overlay(post_id: str, overlay: str, profile_slug=None) -> dict:
    """Append one slide_overlays row to an existing brief (sync via reindex)."""
    text = (overlay or "").strip()
    if not text:
        raise ActionError("overlay text is required")
    ctx = find_post(post_id, profile_slug)
    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if not brief_file.exists():
        raise ActionError(f"no brief for post '{post_id}' — generate draft first")
    try:
        brief = json.loads(brief_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionError(f"brief file unreadable: {exc}") from exc
    if not isinstance(brief, dict):
        raise ActionError("brief must be a JSON object")
    slides = brief.get("slide_overlays")
    if not isinstance(slides, list):
        slides = []
    next_n = 1
    for item in slides:
        if isinstance(item, dict) and item.get("slide"):
            try:
                next_n = max(next_n, int(item["slide"]) + 1)
            except (TypeError, ValueError):
                pass
    slides.append({"slide": next_n, "overlay": text})
    brief["slide_overlays"] = slides
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if lines:
        title = lines[0]
        tail = lines[2] if len(lines) > 2 else (lines[1] if len(lines) > 1 else "")
        bullet = f"• {title}. {tail}" if tail else f"• {title}"
        cap = brief.get("caption") or ""
        if bullet not in cap:
            for marker in ("\n\nWhich", "\n\n#", "\n\nAnd "):
                idx = cap.find(marker)
                if idx != -1:
                    cap = cap[:idx].rstrip() + "\n" + bullet + cap[idx:]
                    break
            else:
                cap = (cap.rstrip() + "\n" + bullet).strip() + "\n"
            brief["caption"] = cap
    result = write_brief(post_id, brief, bump_version_if_exists=True, strict_spec=False,
                          profile_slug=profile_slug)
    return {
        **result,
        "slide": next_n,
        "field_id": _composed_id(lk_fld_brief(post_id, f"slide-{next_n}")),
    }


def delete_post(post_id, profile_slug=None):
    """Remove a slot (and its brief file, if any), then re-index."""
    ctx = find_post(post_id, profile_slug)
    ctx["data"]["posts"] = [p for p in ctx["data"]["posts"] if p.get("id") != post_id]
    brief = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if brief.exists():
        brief.unlink()
    _write_plan(ctx)
    reindex()
    return {"id": post_id, "deleted": True}


def delete_posts(post_ids, profile_slug=None):
    """Delete several slots in one pass (one re-index). Unknown ids are skipped.

    Touches each plan file at most once so a multi-select delete is a single
    write + rebuild rather than N of them."""
    wanted = {str(i) for i in (post_ids or [])}
    if not wanted:
        return {"deleted": [], "count": 0}
    deleted = []
    plan_glob = (
        ROOT.glob(f"projects/*/profiles/{profile_slug}/content/plan-*.json")
        if profile_slug
        else ROOT.glob("projects/*/profiles/*/content/plan-*.json")
    )
    for plan in sorted(plan_glob):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        posts = data.get("posts", []) if isinstance(data, dict) else []
        hit = [p for p in posts if p.get("id") in wanted]
        if not hit:
            continue
        data["posts"] = [p for p in posts if p.get("id") not in wanted]
        for p in hit:
            brief = plan.parent / "briefs" / f"{p.get('id')}.json"
            if brief.exists():
                brief.unlink()
            deleted.append(p.get("id"))
        plan.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"deleted": deleted, "count": len(deleted)}


def _slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def create_project(slug: str, fields: dict) -> dict:
    slug = slug.strip()
    if not slug:
        raise ActionError("slug is required")
    project_dir = ROOT / "projects" / slug
    if project_dir.exists():
        raise ActionError(f"project '{slug}' already exists")
    name = (fields.get("name") or slug).strip()
    kind = fields.get("kind") or "venture"
    priority = fields.get("priority") or "primary"
    status = fields.get("status") or "idea"
    hours = str(fields.get("hours_per_week") or "0")
    voice = (fields.get("voice") or "").strip()
    for sub in ["profiles", "products", "strategy/memos", "strategy/experiments"]:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    md = f"---\nname: {name}\nkind: {kind}\npriority: {priority}\nhours_per_week: {hours}\nstatus: {status}\n---\n{voice}\n"
    (project_dir / "project.md").write_text(md, encoding="utf-8")
    ensure_config(ROOT, slug)
    reindex()
    return {"slug": slug}


def update_project(slug: str, fields: dict) -> dict:
    """Rewrite project.md frontmatter (name/kind/priority/status/hours), keep body.
    The slug is identity (it's the directory name + every reference key), so it is
    NOT changed here — only the display name and metadata are editable."""
    f = ROOT / "projects" / slug / "project.md"
    if not f.exists():
        raise ActionError(f"project '{slug}' not found")
    fm, body = _parse_frontmatter(f.read_text(encoding="utf-8"))
    name = (fields.get("name") or fm.get("name") or slug).strip()
    kind = (fields.get("kind") or fm.get("kind") or "venture").strip()
    priority = (fields.get("priority") or fm.get("priority") or "primary").strip()
    status = (fields.get("status") or fm.get("status") or "idea").strip()
    hours = str(fields.get("hours_per_week") or fm.get("hours_per_week") or "0").strip()
    md = (f"---\nname: {name}\nkind: {kind}\npriority: {priority}\n"
          f"hours_per_week: {hours}\nstatus: {status}\n---\n{body}\n")
    f.write_text(md, encoding="utf-8")
    reindex()
    return {"slug": slug}


def _portfolio_refs(slug: str) -> list:
    """Portfolio activities/milestones that reference this entity slug. These live
    OUTSIDE the project tree, so deleting the tree would leave them dangling and
    break the next re-index's slug integrity check — callers refuse on non-empty."""
    refs = []
    acts = ROOT / "portfolio" / "activities.md"
    if acts.exists():
        pat = re.compile(rf"entity:\s*{re.escape(slug)}(?![\w-])")
        for line in acts.read_text(encoding="utf-8").splitlines():
            if pat.search(line):
                m = re.match(r"^- \[[ x]\]\s*(.*?)(?:\s+—|$)", line)
                refs.append(f"activity '{(m.group(1) if m else line).strip()}'")
    ms = ROOT / "portfolio" / "milestones.json"
    if ms.exists():
        try:
            data = json.loads(ms.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for m in data.get("milestones", []) if isinstance(data, dict) else []:
            if m.get("entity") == slug:
                refs.append(f"milestone '{m.get('title') or m.get('id')}'")
    return refs


def delete_project(slug: str) -> dict:
    """Remove a project tree, refusing if portfolio items still reference it."""
    import shutil
    project_dir = ROOT / "projects" / slug
    if not project_dir.exists():
        raise ActionError(f"project '{slug}' not found")
    refs = _portfolio_refs(slug)
    if refs:
        raise ActionError(
            f"cannot delete '{slug}' — still referenced by {', '.join(refs)}."
            " Remove or reassign these first.")
    shutil.rmtree(project_dir)
    reindex()
    return {"slug": slug, "deleted": True}


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


def create_channel(profile_slug: str, slug: str, platform: str, handle: str = "") -> dict:
    profile_dir = _profile_dir(profile_slug)
    channel_dir = profile_dir / "channels" / slug
    if channel_dir.exists():
        raise ActionError(f"channel '{slug}' already exists")
    channel_dir.mkdir(parents=True, exist_ok=True)
    handle_line = f"handle: {handle}\n" if handle.strip() else ""
    md = f"---\nplatform: {platform}\n{handle_line}---\n"
    (channel_dir / "channel.md").write_text(md, encoding="utf-8")
    (channel_dir / "guidelines.md").write_text("", encoding="utf-8")
    reindex()
    return {"slug": slug, "profile": profile_slug, "platform": platform}


def update_channel(slug: str, fields: dict) -> dict:
    """Rewrite channel.md frontmatter (platform/handle/name), keep body.
    guidelines.md is a separate authored file and is left untouched."""
    f = _channel_dir(slug) / "channel.md"  # _channel_dir raises if slug unknown
    fm, body = _parse_frontmatter(f.read_text(encoding="utf-8")) if f.exists() else ({}, "")
    platform = (fields.get("platform") or fm.get("platform") or "").strip()
    raw_handle = fields.get("handle") if fields.get("handle") is not None else fm.get("handle", "")
    handle = (raw_handle or "").strip()
    name = (fields.get("name") or fm.get("name") or "").strip()
    bio = (fields.get("bio") or fm.get("bio") or "").strip()
    lines = [f"platform: {platform}"]
    if handle:
        lines.append(f"handle: {handle}")
    if name:
        lines.append(f"name: {name}")
    if bio:
        lines.append(f"bio: {bio}")
    md = "---\n" + "\n".join(lines) + "\n---\n" + (f"{body}\n" if body else "")
    f.write_text(md, encoding="utf-8")
    reindex()
    return {"slug": slug}


def delete_channel(slug: str) -> dict:
    import shutil
    shutil.rmtree(_channel_dir(slug))
    reindex()
    return {"slug": slug, "deleted": True}


def delete_profile(slug: str) -> dict:
    import shutil
    shutil.rmtree(_profile_dir(slug))
    reindex()
    return {"slug": slug, "deleted": True}


def delete_activity(title: str) -> dict:
    path = ROOT / "portfolio" / "activities.md"
    if not path.exists():
        raise ActionError("activities.md not found")
    text = path.read_text(encoding="utf-8")
    escaped = re.escape(title)
    new_text, n = re.subn(
        rf"^- \[[ x]\] {escaped}[^\n]*\n?", "", text, flags=re.MULTILINE
    )
    if n == 0:
        raise ActionError(f"activity '{title}' not found")
    path.write_text(new_text, encoding="utf-8")
    reindex()
    return {"title": title, "deleted": True}


def mark_activity_done(title: str, entity_slug: str) -> dict:
    """Mark an activity as done in portfolio/activities.md by checking its checkbox."""
    path = ROOT / "portfolio" / "activities.md"
    if not path.exists():
        raise ActionError("activities.md not found")
    text = path.read_text(encoding="utf-8")
    # Match the exact line and flip the checkbox
    escaped = re.escape(title)
    new_text, n = re.subn(
        rf"^(- )\[ \] ({escaped}.*)$",
        r"\1[x] \2",
        text,
        flags=re.MULTILINE,
    )
    if n == 0:
        raise ActionError(f"activity '{title}' not found or already done")
    path.write_text(new_text, encoding="utf-8")
    reindex()
    return {"title": title, "done": True}


def create_activity(fields: dict) -> dict:
    entity = (fields.get("entity") or "").strip()
    title = (fields.get("title") or "").strip()
    if not title:
        raise ActionError("title is required")
    if not entity:
        raise ActionError("entity (project slug) is required")
    portfolio = ROOT / "portfolio"
    portfolio.mkdir(exist_ok=True)
    path = portfolio / "activities.md"
    date = (fields.get("date") or "").strip()
    date_end = (fields.get("date_end") or "").strip()
    type_ = (fields.get("type") or "task").strip()
    priority = (fields.get("priority") or "").strip()
    existing_ids: set[str] = set()
    if path.exists():
        for _sec, _chk, _title, fields in _parse_activities(path.read_text(encoding="utf-8")):
            if fields.get("id"):
                existing_ids.add(str(fields["id"]))
    act_id = next_activity_id(existing_ids)
    parts = [title, f"id: {act_id}", f"entity: {entity}"]
    if date:
        parts.append(f"date: {date}")
    if date_end:
        parts.append(f"date_end: {date_end}")
    if type_:
        parts.append(f"type: {type_}")
    if priority in {"primary", "secondary", "experiment"}:
        parts.append(f"priority: {priority}")
    line = "- [ ] " + " — ".join(parts) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip("\n") + "\n" + line, encoding="utf-8")
    else:
        path.write_text(f"## Activities\n{line}", encoding="utf-8")
    reindex()
    return {"id": act_id, "title": title, "entity": entity}


def _parse_activities(text: str):
    """Reuse index.parse_checklist without importing index at module load."""
    import index
    return index.parse_checklist(text)


def create_milestone(fields: dict) -> dict:
    title = (fields.get("title") or "").strip()
    date = (fields.get("date") or "").strip()
    if not title:
        raise ActionError("title is required")
    if not date:
        raise ActionError("date is required")
    entity = (fields.get("entity") or "").strip()
    portfolio = ROOT / "portfolio"
    portfolio.mkdir(exist_ok=True)
    path = portfolio / "milestones.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"milestones": []}
        if not isinstance(data, dict):
            data = {"milestones": []}
    else:
        data = {"milestones": []}
    existing_ids = {m.get("id") for m in data.get("milestones", [])}
    ms_id = next_milestone_id(existing_ids)
    ms: dict = {"id": ms_id, "title": title, "date": date,
                "type": (fields.get("type") or "event").strip(),
                "entity_type": (fields.get("entity_type") or "project").strip()}
    if entity:
        ms["entity"] = entity
    if fields.get("date_end"):
        ms["date_end"] = fields["date_end"].strip()
    if fields.get("notes"):
        ms["notes"] = fields["notes"].strip()
    if fields.get("priority") in {"primary", "secondary", "experiment"}:
        ms["priority"] = fields["priority"]
    data.setdefault("milestones", []).append(ms)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": ms_id, "title": title}


_MILESTONE_FIELDS = ("title", "date", "date_end", "type", "entity", "entity_type",
                     "notes", "priority")


def _load_milestones(path):
    if not path.exists():
        raise ActionError("milestones.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ActionError("milestones.json is not valid JSON")
    if not isinstance(data, dict) or not isinstance(data.get("milestones"), list):
        raise ActionError("milestones.json has an unexpected shape")
    return data


def update_milestone(ms_id: str, fields: dict) -> dict:
    """Edit one milestone in milestones.json. Empty values clear the field."""
    path = ROOT / "portfolio" / "milestones.json"
    data = _load_milestones(path)
    for m in data["milestones"]:
        if m.get("id") == ms_id:
            for k in _MILESTONE_FIELDS:
                if k not in fields or fields[k] is None:
                    continue
                v = str(fields[k]).strip()
                if v:
                    m[k] = v
                else:
                    m.pop(k, None)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            reindex()
            return {"id": ms_id}
    raise ActionError(f"milestone '{ms_id}' not found")


def delete_milestone(ms_id: str) -> dict:
    path = ROOT / "portfolio" / "milestones.json"
    data = _load_milestones(path)
    kept = [m for m in data["milestones"] if m.get("id") != ms_id]
    if len(kept) == len(data["milestones"]):
        raise ActionError(f"milestone '{ms_id}' not found")
    data["milestones"] = kept
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": ms_id, "deleted": True}


def _roadmap_section_name(raw: str, project_slug: str) -> str:
    section = (raw or "Next").strip() or "Next"
    low = section.lower()
    if low in ROADMAP_SECTION_ALIASES:
        return ROADMAP_SECTION_ALIASES[low]
    sections = subsections_for_doc(load_config(ROOT, project_slug), "roadmap")
    for s in sections:
        if s.lower() == low:
            return s
    raise ActionError(
        f"unknown roadmap section '{section}' — use one of: {', '.join(sections)}"
    )


def read_subsections(project_slug: str) -> dict:
    """Load subsection config; writes default subsections.json if missing."""
    _project_dir(project_slug)
    return subsections_api_payload(ensure_config(ROOT, project_slug))


def _project_doc_path(project_slug: str, doc_key: str) -> Path | None:
    rel = DOC_META.get(doc_key, {}).get("path")
    if not rel or "<" in rel:
        return None
    return _project_dir(project_slug) / rel


def _write_project_doc(project_slug: str, doc_key: str, text: str, *, path: Path) -> str:
    cfg = load_config(ROOT, project_slug)
    norm, cfg = normalize_doc_text(text, doc_key=doc_key, config=cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(norm, encoding="utf-8")
    save_config(ROOT, project_slug, cfg)
    return norm


def _normalize_doc_strict(project_slug: str, doc_key: str, text: str, cfg: dict) -> str:
    """Normalize markdown to config subsections only — no heading merge."""
    meta = DOC_META[doc_key]
    sections = subsections_for_doc(cfg, doc_key)
    return normalize_markdown(
        text,
        title=meta["title"],
        sections=sections,
        roadmap=doc_key == "roadmap",
    )


def update_subsections(project_slug: str, doc_key: str, titles: list[str]) -> dict:
    _project_dir(project_slug)
    cfg = set_doc_subsections(load_config(ROOT, project_slug), doc_key, titles)
    save_config(ROOT, project_slug, cfg)
    doc_path = _project_doc_path(project_slug, doc_key)
    if doc_path and doc_path.is_file():
        norm = _normalize_doc_strict(
            project_slug, doc_key, doc_path.read_text(encoding="utf-8"), cfg,
        )
        doc_path.write_text(norm, encoding="utf-8")
    reindex()
    return {"project": project_slug, "doc": doc_key, "subsections": subsections_api_payload(cfg)}


def update_validation_tab(project_slug: str, titles: list[str]) -> dict:
    _project_dir(project_slug)
    try:
        cfg = set_validation_tab_subsections(load_config(ROOT, project_slug), titles)
    except ValueError as exc:
        raise ActionError(str(exc)) from exc
    save_config(ROOT, project_slug, cfg)
    reindex()
    return {
        "project": project_slug,
        "validation_tab": list(validation_tab_subsections(cfg)),
        "subsections": subsections_api_payload(cfg),
    }


def add_subsection(project_slug: str, doc_key: str, title: str) -> dict:
    _project_dir(project_slug)
    cfg = add_doc_subsection(load_config(ROOT, project_slug), doc_key, title)
    save_config(ROOT, project_slug, cfg)
    doc_path = _project_doc_path(project_slug, doc_key)
    if doc_path and doc_path.is_file():
        norm = _normalize_doc_strict(
            project_slug, doc_key, doc_path.read_text(encoding="utf-8"), cfg,
        )
        doc_path.write_text(norm, encoding="utf-8")
    reindex()
    return {"project": project_slug, "doc": doc_key, "title": title.strip(),
            "subsections": subsections_api_payload(cfg)}


def update_doc_section(project_slug: str, doc_key: str, title: str, body: str) -> dict:
    """Patch one ``##`` subsection body inside intake.md or technical.md."""
    title = (title or "").strip()
    if not title:
        raise ActionError("title required")
    if doc_key not in ("intake", "technical"):
        raise ActionError("doc must be intake or technical")
    _project_dir(project_slug)
    doc_path = _project_doc_path(project_slug, doc_key)
    if not doc_path or not doc_path.is_file():
        raise ActionError(f"{doc_key} file missing — create it first")
    cfg = load_config(ROOT, project_slug)
    sections = tuple(subsections_for_doc(cfg, doc_key))
    if title not in sections:
        raise ActionError(f"subsection '{title}' not in config — add it first")
    meta = DOC_META[doc_key]
    roadmap = doc_key == "roadmap"
    parsed = parse_markdown_sections(doc_path.read_text(encoding="utf-8"), roadmap=roadmap)
    parsed[title] = (body or "").strip()
    chunks = [f"# {meta['title']}", ""]
    for sec in sections:
        chunks.extend([f"## {sec}", "", (parsed.get(sec) or "").strip(), ""])
    draft = "\n".join(chunks).rstrip() + "\n"
    norm = _write_project_doc(project_slug, doc_key, draft, path=doc_path)
    reindex()
    return {
        "project": project_slug,
        "doc": doc_key,
        "title": title,
        "path": str(doc_path.relative_to(ROOT)),
        "chars": len(norm),
    }


def _project_dir(project_slug: str) -> Path:
    d = ROOT / "projects" / project_slug
    if not d.is_dir():
        raise ActionError(f"project '{project_slug}' not found")
    return d


def _product_dir(product_slug: str) -> tuple[Path, str]:
    """Return (product folder, owning project slug)."""
    projects = ROOT / "projects"
    for proj in sorted(projects.glob("*")) if projects.is_dir() else []:
        if not proj.is_dir():
            continue
        d = proj / "products" / product_slug
        if d.is_dir():
            return d, proj.name
    raise ActionError(f"product '{product_slug}' not found")


def create_intake(project_slug: str) -> dict:
    project_dir = _project_dir(project_slug)
    intake = project_dir / "strategy" / "intake.md"
    if intake.exists():
        raise ActionError("intake.md already exists")
    cfg = ensure_config(ROOT, project_slug)
    intake.parent.mkdir(parents=True, exist_ok=True)
    intake.write_text(starter_text(cfg, "intake"), encoding="utf-8")
    reindex()
    rel = str(intake.relative_to(ROOT))
    return {"path": rel, "project": project_slug}


def write_intake(project_slug: str, text: str) -> dict:
    """Replace strategy/intake.md (creates parent dirs if needed)."""
    if not (text or "").strip():
        raise ActionError("intake text required")
    intake = _project_dir(project_slug) / "strategy" / "intake.md"
    _write_project_doc(project_slug, "intake", text, path=intake)
    reindex()
    return {"path": str(intake.relative_to(ROOT)), "project": project_slug}


def create_technical(project_slug: str) -> dict:
    project_dir = _project_dir(project_slug)
    technical = project_dir / "technical.md"
    if technical.exists():
        raise ActionError("technical.md already exists")
    cfg = ensure_config(ROOT, project_slug)
    technical.write_text(starter_text(cfg, "technical"), encoding="utf-8")
    reindex()
    rel = str(technical.relative_to(ROOT))
    return {"path": rel, "project": project_slug}


def write_technical(project_slug: str, text: str) -> dict:
    """Replace technical.md (creates file if needed)."""
    if not (text or "").strip():
        raise ActionError("technical text required")
    technical = _project_dir(project_slug) / "technical.md"
    _write_project_doc(project_slug, "technical", text, path=technical)
    reindex()
    return {"path": str(technical.relative_to(ROOT)), "project": project_slug}


def create_memo(project_slug: str, memo_type: str, fields: dict | None = None,
                body_extra: dict | None = None) -> dict:
    mtype = (memo_type or "").strip()
    if mtype not in MEMO_TYPES:
        raise ActionError(f"unknown memo type '{mtype}'")
    project_dir = _project_dir(project_slug)
    memo_dir = project_dir / "strategy" / "memos"
    memo_dir.mkdir(parents=True, exist_ok=True)
    version = next_memo_version(memo_dir, mtype)
    merged: dict = {}
    if body_extra:
        merged.update(body_extra)
    if fields:
        merged.update({k: v for k, v in fields.items() if v is not None})
    body = normalize_memo_body(mtype, merged, version=version)
    fname = f"{mtype}-v{version}.json"
    path = memo_dir / fname
    path.write_text(dumps_json(body), encoding="utf-8")
    reindex()
    key = lk_memo(project_slug, mtype, version)
    rel = str(path.relative_to(ROOT))
    return {"id": _composed_id(key), "type": mtype, "version": version, "path": rel, "project": project_slug}


def create_experiment(project_slug: str, fields: dict) -> dict:
    assumption = (fields.get("assumption") or fields.get("assumption_under_test") or "").strip()
    if not assumption:
        raise ActionError("assumption is required")
    project_dir = _project_dir(project_slug)
    exp_dir = project_dir / "strategy" / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    stem = (fields.get("stem") or "").strip() or next_experiment_stem(exp_dir)
    stem = _slugify(stem) or next_experiment_stem(exp_dir)
    path = exp_dir / f"{stem}.json"
    if path.exists():
        raise ActionError(f"experiment '{stem}' already exists")
    body = normalize_experiment_body({**fields, "assumption": assumption})
    path.write_text(dumps_json(body), encoding="utf-8")
    reindex()
    rel = str(path.relative_to(ROOT))
    return {
        "id": _composed_id(lk_experiment(project_slug, stem)),
        "stem": stem,
        "path": rel,
        "project": project_slug,
        "assumption": assumption,
    }


def update_experiment(project_slug: str, stem: str, fields: dict) -> dict:
    """Patch an existing experiment JSON by stem."""
    stem = (stem or "").strip()
    if not stem:
        raise ActionError("stem is required")
    path = _project_dir(project_slug) / "strategy" / "experiments" / f"{stem}.json"
    if not path.exists():
        raise ActionError(f"experiment '{stem}' not found")
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ActionError(f"experiment '{stem}' is not a JSON object")
    patch = dict(body)
    for key in ("assumption", "assumption_under_test", "success_criteria", "kill_criteria", "status"):
        if key in fields and fields[key] is not None:
            patch[key] = fields[key]
    body = normalize_experiment_body(patch)
    path.write_text(dumps_json(body), encoding="utf-8")
    reindex()
    rel = str(path.relative_to(ROOT))
    return {
        "id": _composed_id(lk_experiment(project_slug, stem)),
        "stem": stem,
        "path": rel,
        "project": project_slug,
    }


def create_product(project_slug: str, slug: str, fields: dict) -> dict:
    slug = (slug or "").strip()
    if not slug:
        raise ActionError("slug is required")
    project_dir = _project_dir(project_slug)
    prod_dir = project_dir / "products" / slug
    if prod_dir.exists():
        raise ActionError(f"product '{slug}' already exists")
    name = (fields.get("name") or slug).strip()
    ptype = (fields.get("type") or "app").strip()
    status = (fields.get("status") or "idea").strip()
    prod_dir.mkdir(parents=True)
    (prod_dir / "product.md").write_text(
        f"---\nname: {name}\ntype: {ptype}\nstatus: {status}\n---\n",
        encoding="utf-8",
    )
    cfg = ensure_config(ROOT, project_slug)
    (prod_dir / "roadmap.md").write_text(starter_text(cfg, "roadmap"), encoding="utf-8")
    reindex()
    return {"id": _composed_id(lk_prod(slug)), "slug": slug, "name": name, "project": project_slug}


def feature_roadmap_details(product_slug: str) -> dict[str, dict]:
    """Parse roadmap.md checklist — map title → why, priority, etc."""
    try:
        prod_dir, _ = _product_dir(product_slug)
    except ActionError:
        return {}
    roadmap = prod_dir / "roadmap.md"
    if not roadmap.is_file():
        return {}
    from index import parse_checklist  # noqa: WPS433
    out: dict[str, dict] = {}
    for sec, _checked, title, flds in parse_checklist(roadmap.read_text(encoding="utf-8")):
        if title:
            row = dict(flds)
            if sec:
                row["roadmap_section"] = sec
            out[title] = row
    return out


def enrich_project_memos(memos: list[dict], project_slug: str, registry) -> list[dict]:
    from core.ids import lk_memo  # noqa: WPS433
    rows = []
    for m in memos or []:
        row = dict(m)
        if registry:
            row["id"] = registry.lookup.get(
                lk_memo(project_slug, m.get("type") or "", int(m.get("version") or 0)))
        rows.append(row)
    return rows


def enrich_project_experiments(experiments: list[dict], project_slug: str, registry) -> list[dict]:
    from core.ids import experiment_stem_from_path, lk_experiment  # noqa: WPS433
    rows = []
    for x in experiments or []:
        row = dict(x)
        stem = row.get("stem") or experiment_stem_from_path(row.get("file_path") or "") or ""
        if registry and stem:
            row["id"] = registry.lookup.get(lk_experiment(project_slug, stem))
        rows.append(row)
    return rows


def enrich_project_features(features: list[dict], registry) -> list[dict]:
    """Attach canonical id + roadmap why/priority from live files."""
    from core.ids import lk_feature, slug_key  # noqa: WPS433
    by_prod: dict[str, dict[str, dict]] = {}
    rows = []
    for f in features or []:
        row = dict(f)
        pslug = row.get("product_slug") or ""
        title = row.get("title") or ""
        if pslug not in by_prod:
            by_prod[pslug] = feature_roadmap_details(pslug)
        det = by_prod[pslug].get(title) or {}
        if det.get("why"):
            row["why"] = det["why"]
        if det.get("priority") and not row.get("priority"):
            row["priority"] = det["priority"]
        if det.get("roadmap_section"):
            row["roadmap_section"] = det["roadmap_section"]
        tk = slug_key(title)
        row["id"] = (registry.lookup.get(lk_feature(pslug, tk)) if registry else None)
        rows.append(row)
    return rows


def add_feature(product_slug: str, fields: dict) -> dict:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ActionError("title is required")
    prod_dir, project_slug = _product_dir(product_slug)
    roadmap = prod_dir / "roadmap.md"
    if not roadmap.exists():
        cfg = ensure_config(ROOT, project_slug)
        roadmap.write_text(starter_text(cfg, "roadmap"), encoding="utf-8")
    section = _roadmap_section_name(fields.get("section") or "Next", project_slug)
    text = _write_project_doc(project_slug, "roadmap", roadmap.read_text(encoding="utf-8"), path=roadmap)
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
    reindex()
    return {
        "id": _composed_id(lk_feature(product_slug, slug_key(title))),
        "title": title,
        "product": product_slug,
        "section": section,
    }


def write_roadmap(product_slug: str, text: str) -> dict:
    """Replace products/<slug>/roadmap.md."""
    if not (text or "").strip():
        raise ActionError("roadmap text required")
    prod_dir, project_slug = _product_dir(product_slug)
    roadmap = prod_dir / "roadmap.md"
    _write_project_doc(project_slug, "roadmap", text, path=roadmap)
    reindex()
    return {
        "path": str(roadmap.relative_to(ROOT)),
        "product": product_slug,
        "project": project_slug,
    }


def read_authored_json(relpath):
    """Read an authored JSON file (memo/experiment body) by its os.db-relative path."""
    if not relpath:
        return None
    f = ROOT / relpath
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_error": "file is not valid JSON"}


def _plan_args(profile_slug, params):
    """Build the generate.py plan argv from UI params. Raises if period is missing."""
    period = (params.get("period") or "").strip()
    if not period:
        raise ActionError("a period is required (e.g. '2026-07-01 to 2026-07-14')")
    args = [sys.executable, str(ROOT / "generate.py"),
            "--workspace", str(ROOT), "plan", profile_slug, "--period", period]
    platforms = (params.get("platforms") or "").strip()
    if platforms:
        args += ["--platforms", platforms]
    cadence = params.get("cadence")
    if cadence not in (None, ""):
        args += ["--cadence", str(int(cadence))]
    focus = (params.get("focus") or "").strip()
    if focus:
        args += ["--focus", focus]
    brief_counts = (params.get("brief_counts") or "").strip()
    if brief_counts:
        args += ["--brief-counts", brief_counts]
    voice_counts = (params.get("voice_counts") or "").strip()
    if voice_counts:
        args += ["--voice-counts", voice_counts]
    return args


def run_plan(profile_slug, params):
    """Generate a content calendar for a profile via claude -p, then re-index."""
    _profile_dir(profile_slug)
    res = subprocess.run(_plan_args(profile_slug, params), capture_output=True, text=True)
    if res.returncode != 0:
        raise ActionError(f"plan job failed: {(res.stderr or res.stdout).strip()[:800]}")
    reindex()
    return {"profile_slug": profile_slug, "stdout": res.stdout.strip()[:400]}
