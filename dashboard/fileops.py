"""fileops.py — WRITE side of the dashboard API.

The dashboard NEVER writes os.db. It mutates the authored source FILE (the plan
JSON / brief JSON), then re-runs index.py so the derived index catches up. This
module is that isolated mutation layer — the server-shaped seam that keeps a
future server migration mechanical.

Pipeline status state machine (lives in the plan file's post object, mirrored to
posts.status on re-index):
    planned -> approved_slot -> briefed -> approved -> scheduled -> published
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

ROOT = Path(__file__).resolve().parent.parent

# index.py is a fixed script (it lives at the repo root); ROOT is the WORKSPACE
# it indexes. They coincide in production but tests point ROOT at a temp dir.
_INDEX_SCRIPT = Path(__file__).resolve().parent.parent / "index.py"

ALLOWED_TRANSITIONS = {
    "planned":       {"approved_slot", "rejected"},
    "approved_slot": {"briefed", "rejected", "planned"},
    "briefed":       {"approved", "rejected", "approved_slot"},
    "approved":      {"scheduled", "rejected"},
    "scheduled":     {"published", "rejected"},
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


def _parse_channels(raw):
    """Parse a comma/space-separated channel slug string into a list of slugs."""
    if not raw:
        return []
    slugs = [s.strip() for s in re.split(r"[,\s]+", raw.strip()) if s.strip()]
    return slugs


def find_post(post_id):
    """Locate the plan file + post object for a post id. Returns a dict context."""
    for plan in sorted(ROOT.glob("projects/*/profiles/*/content/plan-*.json")):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for post in data.get("posts", []) if isinstance(data, dict) else []:
            if post.get("id") == post_id:
                # projects/<proj>/profiles/<profile>/content/plan-*.json
                profile_slug = plan.parent.parent.name
                return {"plan": plan, "data": data, "post": post, "profile_slug": profile_slug}
    raise ActionError(f"post '{post_id}' not found in any plan file")


def _write_plan(ctx):
    ctx["plan"].write_text(
        json.dumps(ctx["data"], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def set_status(post_id, new_status):
    """Transition a post's status in its plan file, then re-index."""
    if new_status not in ALLOWED_TRANSITIONS:
        raise ActionError(f"unknown status '{new_status}'")
    ctx = find_post(post_id)
    current = ctx["post"].get("status") or "planned"
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


def generate_brief(post_id):
    """Run the claude -p brief job for an approved slot, then mark it briefed.

    Brief generation is the 'enqueue a claude -p job' step — synchronous here.
    generate.py writes the brief file; we then advance status and re-index.
    """
    ctx = find_post(post_id)
    current = ctx["post"].get("status") or "planned"
    if current not in ("planned", "approved_slot"):
        raise ActionError(f"can only brief a planned/approved_slot post (is '{current}')")

    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    is_rebrief = brief_file.exists()  # regenerating an existing brief = a new version

    res = subprocess.run(
        [sys.executable, str(ROOT / "generate.py"),
         "--workspace", str(ROOT), "brief", ctx["profile_slug"], post_id],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise ActionError(f"brief job failed: {(res.stderr or res.stdout).strip()[:800]}")

    # re-read, advance status; a re-brief bumps version (edits create a new version)
    ctx = find_post(post_id)
    ctx["post"]["status"] = "briefed"
    if is_rebrief:
        ctx["post"]["version"] = int(ctx["post"].get("version") or 1) + 1
    _write_plan(ctx)
    reindex()
    return {"id": post_id, "status": "briefed", "stdout": res.stdout.strip()}


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


def read_brief_spec(slug):
    """The profile's brief spec: free-text requirements every post must meet
    (e.g. caption length, hashtag count, format leanings). Injected into every
    brief job for this profile. Authored file, not indexed."""
    f = _profile_dir(slug) / "brief-spec.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def read_profile(slug):
    """Read profile.md and return name, topic, voice, project, and brief spec."""
    d = _profile_dir(slug)
    f = d / "profile.md"
    if not f.exists():
        return {"slug": slug, "name": slug, "topic": "", "voice": "",
                "project": "", "brief_spec": ""}
    fm, body = _parse_frontmatter(f.read_text(encoding="utf-8"))
    return {"slug": slug, "name": fm.get("name", slug),
            "topic": fm.get("topic", ""), "voice": body,
            "project": fm.get("project", ""),
            "brief_spec": read_brief_spec(slug)}


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


def read_detail(post_id):
    """Authored detail for a post: the plan slot + the brief JSON if it exists.

    Prose/authored content is read from FILES (their source of truth), while the
    coordination fields come from os.db via db.py.
    """
    ctx = find_post(post_id)
    brief = None
    brief_file = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if brief_file.exists():
        try:
            brief = json.loads(brief_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            brief = {"_error": "brief file is not valid JSON"}
    return {"slot": ctx["post"], "brief": brief, "profile_slug": ctx["profile_slug"]}


_POST_FIELDS = ("date", "pillar", "working_title", "concept")


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
    existing = {p.get("id") for p in data["posts"]}
    pid = "m-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    while pid in existing:
        pid += "x"
    post = {"id": pid, "status": "planned"}
    for k in _POST_FIELDS:
        v = (fields.get(k) or "").strip()
        if v:
            post[k] = v
    channels = _parse_channels(fields.get("channels"))
    if channels:
        post["channels"] = channels
    data["posts"].append(post)
    plan.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    reindex()
    return {"id": pid, "profile_slug": profile_slug}


def update_post(post_id, fields):
    """Edit a slot's authored fields in its plan file, then re-index."""
    ctx = find_post(post_id)
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
    _write_plan(ctx)
    reindex()
    return {"id": post_id}


def delete_post(post_id):
    """Remove a slot (and its brief file, if any), then re-index."""
    ctx = find_post(post_id)
    ctx["data"]["posts"] = [p for p in ctx["data"]["posts"] if p.get("id") != post_id]
    brief = ctx["plan"].parent / "briefs" / f"{post_id}.json"
    if brief.exists():
        brief.unlink()
    _write_plan(ctx)
    reindex()
    return {"id": post_id, "deleted": True}


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
    voice = (fields.get("voice") or "").strip()
    for sub in ["content/briefs", "channels"]:
        (profile_dir / sub).mkdir(parents=True, exist_ok=True)
    md = f"---\nname: {name}\ntopic: {topic}\nproject: {project_slug}\n---\n{voice}\n"
    (profile_dir / "profile.md").write_text(md, encoding="utf-8")
    reindex()
    return {"slug": slug, "project": project_slug}


def update_profile(slug: str, fields: dict) -> dict:
    """Rewrite profile.md frontmatter (name/topic) and body (voice), keep structure."""
    profile_dir = _profile_dir(slug)  # raises if not found
    f = profile_dir / "profile.md"
    fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8")) if f.exists() else ({}, "")
    name = (fields.get("name") or fm.get("name") or slug).strip()
    topic = (fields.get("topic") if fields.get("topic") is not None else fm.get("topic", "")).strip()
    project = fm.get("project", "")
    voice = (fields.get("voice") if fields.get("voice") is not None else "").strip()
    md = f"---\nname: {name}\ntopic: {topic}\nproject: {project}\n---\n{voice}\n"
    f.write_text(md, encoding="utf-8")
    # Brief spec lives in its own authored file (free text, not indexed).
    if fields.get("brief_spec") is not None:
        (profile_dir / "brief-spec.md").write_text(
            fields["brief_spec"].strip() + "\n", encoding="utf-8")
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
    lines = [f"platform: {platform}"]
    if handle:
        lines.append(f"handle: {handle}")
    if name:
        lines.append(f"name: {name}")
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
    parts = [title, f"entity: {entity}"]
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
    return {"title": title, "entity": entity}


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
    ms_id = "ms-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    while ms_id in existing_ids:
        ms_id += "x"
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
    return args


def run_plan(profile_slug, params):
    """Generate a content calendar for a profile via claude -p, then re-index."""
    _profile_dir(profile_slug)
    res = subprocess.run(_plan_args(profile_slug, params), capture_output=True, text=True)
    if res.returncode != 0:
        raise ActionError(f"plan job failed: {(res.stderr or res.stdout).strip()[:800]}")
    reindex()
    return {"profile_slug": profile_slug, "stdout": res.stdout.strip()[:400]}
