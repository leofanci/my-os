#!/usr/bin/env python3
"""server.py — the thin local dashboard for the myOS.

Architecture (locked): Python stdlib http.server, a clean JSON API over READ-side
db.py and WRITE-side fileops.py, serving a single static app.html. Reads come from
os.db (read-only); writes mutate FILES then re-index. The dashboard never writes
os.db directly. This is 'server-shaped' on purpose — porting to a real server is
add-an-ASGI-host + auth, no rewrite.

Run:  python3 dashboard/server.py [--port 8765]
"""

import argparse
import base64
import binascii
import hmac
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import db                # noqa: E402
import fileops           # noqa: E402
import chat_session      # noqa: E402
import chat_store        # noqa: E402
import tokensave_bridge  # noqa: E402
import ws                # noqa: E402
import terminal_session  # noqa: E402
from ai_rules import CHAT_RAIL  # noqa: E402
from core.project_schemas import schemas_for_api  # noqa: E402
from core.ids import (  # noqa: E402
    PROJECT_SECTIONS,
    bare_slug,
    build_catalog,
    build_id_registry,
    build_project_sections,
    catalog_as_text,
    describe_id,
    subsection_id_map,
    lk_tab_proj,
    parse_id,
    section_tally,
)

APP_HTML = HERE / "app.html"
AUTH_COOKIE = "myos_auth"
AUTH_TOKEN = secrets.token_urlsafe(32)
MAX_JSON_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_WS_PAYLOAD = 1024 * 1024
UPLOAD_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})

RAIL = CHAT_RAIL

# Profile "numbered artifact" routes (brief-specs, voices) — same CRUD shape
# for both, so GET/POST dispatch loops over this instead of repeating
# near-identical branches per kind. Every fn's positional signature lines up:
# list(slug), get(slug, id), create(slug, text, platforms), update(slug, text,
# id, platforms), delete(slug, id).
_ARTIFACT_ROUTES = {
    "brief-specs": {
        "list_key": "specs",
        "list": fileops.list_brief_specs,
        "get": fileops.get_brief_spec,
        "create": fileops.create_brief_spec,
        "update": fileops.write_brief_spec,
        "delete": fileops.delete_brief_spec,
    },
    "voices": {
        "list_key": "voices",
        "list": fileops.list_voices,
        "get": fileops.get_voice,
        "create": fileops.create_voice,
        "update": fileops.update_voice,
        "delete": fileops.delete_voice,
    },
}


def _app_html_bytes() -> bytes:
    """Serve app.html with cache-busted asset URLs (mtime) so UI updates land."""
    html = APP_HTML.read_text(encoding="utf-8")
    for name in ("ui-tokens.css", "app.css", "app.js", "os-ids.js", "post-copy.js", "logo.svg"):
        v = int((HERE / name).stat().st_mtime)
        html = html.replace(f"/{name}\"", f"/{name}?v={v}\"")
    return html.encode("utf-8")


def pick_local_folder() -> dict:
    """Show the macOS folder chooser and return its absolute POSIX path."""
    if sys.platform != "darwin":
        raise fileops.ActionError("the folder chooser is currently available on macOS")
    result = subprocess.run(
        ["/usr/bin/osascript", "-e",
         'POSIX path of (choose folder with prompt "Choose the app folder to link")'],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if "User canceled" in message or "(-128)" in message:
            return {"path": None, "cancelled": True}
        raise fileops.ActionError(f"folder chooser failed: {message or 'unknown error'}")
    path = fileops.normalize_local_folder(result.stdout.strip())
    return {"path": path, "cancelled": False}


def open_local_folder(path: str) -> None:
    """Open a validated linked directory in the platform file manager."""
    if sys.platform == "darwin":
        command = ["/usr/bin/open", path]
    elif sys.platform.startswith("linux"):
        command = ["xdg-open", path]
    else:
        raise fileops.ActionError("opening linked folders is not supported on this platform")
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise fileops.ActionError(f"could not open linked folder: {message or 'unknown error'}")


def resolve_linked_workspace(projects, project_slug):
    """Resolve the active project's saved app folder without trusting a client path.

    The client sends only a slug. It must match the indexed project tree, and the
    actual path is then read from authored project.md and revalidated. A missing
    or stale link never breaks chat; it simply leaves app tools disabled.
    """
    slug = str(project_slug or "").strip()
    if not slug:
        return None
    project = next((p for p in projects if p.get("slug") == slug), None)
    if not project or not project.get("local_folder"):
        return None
    try:
        return fileops.project_local_folder(slug)
    except (fileops.ActionError, OSError):
        return None


def tokensave_index_ready(workspace_dir):
    """Cheap readiness check; never starts TokenSave or scans the app."""
    return bool(
        workspace_dir
        and shutil.which("tokensave")
        and (Path(workspace_dir) / ".tokensave" / "tokensave.db").is_file()
    )


def linked_workspace_prompt(project_slug, workspace_dir, *, graph_context="",
                            graph_error=None, file_search_mode=False):
    """Bounded app evidence plus an optional pointer for lazy file fallback."""
    if not workspace_dir:
        return ""
    if graph_context:
        guidance = (
            "myOS already refreshed and queried this app's TokenSave graph exactly "
            "once for this turn. Use the bounded result below as product evidence "
            "for GTM, positioning, branding, ICP, offer, social/content, feature, "
            "UX, and technical reasoning. Do not run TokenSave again."
        )
    elif graph_error:
        guidance = (
            f"TokenSave could not provide fresh context ({graph_error}). No stale "
            "graph result was used."
        )
    else:
        guidance = (
            "This app has no ready local TokenSave index. Use bounded file discovery "
            "when product facts from the app could improve the answer."
        )
    fallback = (
        " If needed, use targeted Glob/Grep, then Read at most 200 relevant lines "
        "at a time."
        if file_search_mode else ""
    )
    root_line = f"App root: {workspace_dir}\n" if file_search_mode else ""
    graph_block = (
        "\n\n## Fresh TokenSave context (bounded, read-only evidence)\n"
        f"{graph_context}"
        if graph_context else ""
    )
    return (
        "## Linked app workspace (read-only)\n"
        f"Active project: {project_slug}\n"
        f"{root_line}{guidance}{fallback}"
        + (" Check a root AGENTS.md/CLAUDE.md first if present."
           if file_search_mode else "")
        + " Skip dependency, build, cache, generated, and secret files. Never edit the linked app."
        + graph_block
    )


def state_snapshot(projects):
    """COMPACT OS index for the chat agent — projects/profiles/channels plus
    per-entity counts, NOT full content. Bounded in size as content grows (the
    old version enumerated every post/memo/activity every turn). The agent pulls
    detail on demand via osctl get-posts / get-project / read-file."""
    lines = ["## Current myOS state",
             "(index only — fetch detail with osctl get-posts / get-project / read-file)"]
    if not projects:
        lines.append("(no projects yet)")
        return "\n".join(lines)

    try:
        post_counts, memo_counts, exp_counts, open_act_counts = {}, {}, {}, {}
        all_memos, all_exps, all_features = db.memos(), db.experiments(), db._rows(
            "SELECT product_slug, title, status FROM features"
        )
        for p in db.posts():
            post_counts[p["profile_slug"]] = post_counts.get(p["profile_slug"], 0) + 1
        for m in all_memos:
            memo_counts[m["entity_slug"]] = memo_counts.get(m["entity_slug"], 0) + 1
        for e in all_exps:
            exp_counts[e["entity_slug"]] = exp_counts.get(e["entity_slug"], 0) + 1
        for a in db._rows("SELECT entity_slug, status FROM activities"):
            if (a["status"] or "") != "done":
                open_act_counts[a["entity_slug"]] = open_act_counts.get(a["entity_slug"], 0) + 1
    except Exception:  # noqa: BLE001
        post_counts = memo_counts = exp_counts = open_act_counts = {}
        all_memos, all_exps, all_features = [], [], []

    reg = build_id_registry(projects, db.posts(), root=ROOT)

    for p in projects:
        slug = p["slug"]
        pr_id = reg.get(f"proj:{slug}") or slug
        head = f"\n### {slug} id={pr_id} ({p.get('kind') or p.get('type')}"
        if p.get("priority"):
            head += f", {p['priority']}"
        head += ")"
        tally = []
        if memo_counts.get(slug):
            tally.append(f"{memo_counts[slug]} memos")
        if exp_counts.get(slug):
            tally.append(f"{exp_counts[slug]} exp")
        if open_act_counts.get(slug):
            tally.append(f"{open_act_counts[slug]} open")
        if tally:
            head += "  [" + " · ".join(tally) + "]"
        lines.append(head)

        proj_memos = [m for m in all_memos if m.get("entity_slug") == slug]
        proj_exps = [e for e in all_exps if e.get("entity_slug") == slug]
        proj_products = p.get("products") or []
        pslugs = {pr["slug"] for pr in proj_products}
        proj_features = [f for f in all_features if f.get("product_slug") in pslugs]

        for key, label in PROJECT_SECTIONS:
            tally = section_tally(
                slug, key, ROOT,
                memos=proj_memos,
                experiments=proj_exps,
                products=proj_products,
                features=proj_features,
            )
            sec_id = reg.get(lk_tab_proj(slug, key)) or key
            lines.append(f"  section {label} id={sec_id} [{tally}]")

        for prof in p.get("profiles", []):
            n = post_counts.get(prof["slug"], 0)
            pf_id = reg.get(f"prof:{prof['slug']}") or prof["slug"]
            lines.append(f"  profile {prof['slug']} id={pf_id} \"{prof['name']}\" [{n} posts]")
            for ch in prof.get("channels", []):
                ch_id = reg.get(f"chan:{ch['slug']}") or ch["slug"]
                lines.append(f"    channel {ch['slug']} id={ch_id} ({ch.get('platform')})")

    return "\n".join(lines)


# --- per-turn routing (skills, web, model) ------------------------------ #
# Instead of loading the whole skill library via the Skill tool (~4k tok of
# discovery just to let the model pick one), the server routes to the ONE
# relevant skill here and injects only its SKILL.md body into the prompt. No
# discovery overhead, no leaked built-in commands. Pure string match — no extra
# model call.
SKILLS_DIR = ROOT / "skills"

# Ordered: first match wins, so put the more specific / earlier-in-loop skills
# first (e.g. problem-validation before gtm-assessment).
_SKILL_ROUTES = [
    ("problem-validation", r"validat\w*|worth (doing|building|it)|is this worth|do people (need|want)|real problem|painkiller|vitamin"),
    ("market-sizing",      r"market siz\w*|siz\w* (the )?market|\bsam\b|\bsom\b|\btam\b|how big is the market|buyer count"),
    ("pricing-strategy",   r"pricing|price point|packaging|how much (should|do) (we|i) charge|what (should|to) charge|willingness to pay"),
    ("competitor-scan",    r"competitor\w*|competitive landscape|rivals|alternatives to|who else (does|is)"),
    ("positioning",        r"position\w*|messaging|how (do|should) we describe|category|differentiat\w*|tagline|value prop"),
    ("channel-strategy",   r"channel strateg\w*|which channel|distribution channel|where (should|do) (i|we) find customers"),
    ("icp-research",       r"\bicp\b|ideal customer|target customer|customer segment|interview guide"),
    ("brand-identity",     r"brand voice|brand identity|tone of voice|off.brand"),
    ("content-brief",      r"content brief|expand (the )?slot|full (post )?brief|write the brief"),
    ("content-plan",       r"content (plan|calendar)|posting schedule|plan (the )?next \w+ (weeks?|days?)"),
    ("copy-variants",      r"copy variant|hook variant|adapt (across|for) channel|variant\w* for test"),
    ("experiment-design",  r"experiment design|design an experiment|cheapest test|success criteria|kill criteria|riskiest assumption"),
    ("experiment-review",  r"experiment review|log (the )?result|persist.{0,4}pivot.{0,4}kill"),
    ("launch-plan",        r"launch plan|launch sequenc\w*|go.live|launch checklist"),
    ("venture-intake",     r"venture intake|new venture|log (new )?evidence|intake interview"),
    ("weekly-review",      r"weekly review|portfolio cadence|week'?s priorit\w*|what needs attention"),
    ("portfolio-timeline", r"portfolio timeline|unified timeline|timeline across"),
    ("portfolio-sync",     r"portfolio sync|cross.entity|coordinate this week"),
    ("portfolio-map",      r"portfolio map|scaffold (the )?folder|new project structure"),
    # Tab-fill must beat product-build — "fill tabs" is left-panel sections, not roadmap-only.
    ("workspace",             r"fill.{0,40}\btabs?\b|fill.{0,40}\bpanel\b|left panel|project sections?|divide.{0,50}\btabs?\b|populate.{0,40}(tabs?|panel|sections?)"),
    ("product-build",      r"product roadmap|build status|feature roadmap|plan (the )?features"),
    ("gtm-assessment",     r"assess\w*|where (do|does) (we|this) stand|pace call|gtm assessment"),
    # workspace is the catch-all dispatcher for strategic asks that matched nothing
    # specific — handled separately in _route_skill so it has lowest priority.
]
SKILL_NAMES = frozenset(name for name, _ in _SKILL_ROUTES) | {"workspace", "tokensave"}
_COMPILED_ROUTES = [(name, re.compile(pat, re.I)) for name, pat in _SKILL_ROUTES]
_MENTION_RE = re.compile(r"[@/]([a-z][a-z0-9-]+)")
# Generic strategic intent with no specific skill → route to the workspace dispatcher.
_STRATEGIC_RE = re.compile(r"\b(strateg\w*|go.to.market|\bgtm\b|business model|grow\w*)\b", re.I)

# Skills that almost always want live external data.
_WEB_SKILLS = frozenset({"competitor-scan", "market-sizing", "icp-research"})


def _explicit_skill(text):
    """Skill active only when user tagged @skill or /skill (picker or typed)."""
    if not text:
        return None
    for m in _MENTION_RE.findall(text.lower()):
        if m in SKILL_NAMES:
            return m
    return None


def _suggest_skill(text):
    """Keyword hint for untagged turns — does not activate skill or Sonnet."""
    if not text:
        return None
    for name, rx in _COMPILED_ROUTES:
        if rx.search(text):
            return name
    return None


def _route_skill(text):
    """Backward-compat alias: explicit tag only."""
    return _explicit_skill(text)


def _needs_web(text, skill=None):
    """Web tools only on explicit `/web` or `@web`, or tagged research skills."""
    if skill in _WEB_SKILLS:
        return True
    if text and ("web" in _MENTION_RE.findall(text.lower())):
        return True
    return False


# Linked app access is activated only for code/app questions. The browser may
# send the active project slug on every turn, but an ordinary GTM question must
# not pay for Glob/Grep schemas or expose the linked directory to that process.
_WORKSPACE_INTENT_RE = re.compile(
    r"(?:\b(?:code|codebase|source code|repo(?:sitory)?|bug|debug(?:ging)?|"
    r"exception|stack trace|function|method|class|component|endpoint|database|"
    r"schema|migration|authentication|auth|login|test suite|frontend|backend|"
    r"dependency|dockerfile|package\.json|pyproject|typescript|javascript|python|"
    r"react|next\.js|git diff)\b|"
    r"\b(?:inspect|search|find|locate|review|trace|fix|refactor|implement|"
    r"check|analy[sz]e|look)\w*"
    r"\b.{0,40}\b(?:app|folder|files?|source|handler|route|api)\b|"
    r"\b(?:linked|local) (?:app )?folder\b|\bhow does (?:my|the) app work\b|"
    r"\b[\w./-]+\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|kt|rb|php|swift|"
    r"c|cc|cpp|h|hpp|sql|vue|svelte|json|toml|ya?ml)\b)",
    re.I,
)


def _needs_workspace(text, skill=None):
    """Pure string classifier: no model call and no filesystem scan."""
    return skill == "tokensave" or bool(_WORKSPACE_INTENT_RE.search(text or ""))


_APP_CONTEXT_RE = re.compile(
    r"\b(?:app|product|feature|roadmap|user|customer|audience|persona|icp|"
    r"position(?:ing)?|brand(?:ing)?|messaging|value prop(?:osition)?|offer|"
    r"social|content|campaign|channel strategy|copy|launch|pricing|market|"
    r"competitor|acquisition|activation|retention|conversion|onboarding|ux|"
    r"gtm|go.to.market|grow(?:th|ing)?|business model|strateg(?:y|ic))\b",
    re.I,
)


def _needs_app_context(text, skill=None, suggest=None):
    """Whether fresh facts from a linked app should enter this model turn.

    This local classifier deliberately errs toward product evidence for routed
    GTM work, while leaving greetings and myOS administration graph-free.
    """
    return bool(
        skill == "tokensave"
        or _needs_workspace(text, skill)
        or skill in SKILL_NAMES
        or suggest in SKILL_NAMES
        or _APP_CONTEXT_RE.search(text or "")
    )


_READ_TURN_RE = re.compile(
    r"^\s*(what|which|how many|list|show|get|read|status|where|who)\b", re.I
)
_WRITE_TURN_RE = re.compile(
    r"\b(save|commit|write|create|update|fill|populate|add|generate|draft|"
    r"validate|assess|design|plan|build|launch|revise|brief)\b",
    re.I,
)
_CONTINUATION_RE = re.compile(
    r"\b(yes|yep|yeah|ok|okay|sure|go ahead|save|commit|do it|approved|"
    r"looks good|next tab|proceed|continue|save all)\b",
    re.I,
)


def _continuation_allowed(session, user_msg):
    """Follow-up on an explicitly tagged skill thread (e.g. "yes save sec02")."""
    if not getattr(session, "_skill_explicit", False) or not getattr(session, "_last_skill", None):
        return False
    return bool(_CONTINUATION_RE.search(user_msg or ""))


def _in_active_skill_thread(session):
    """True once a turn this session has explicitly tagged a skill — independent
    of _continuation_allowed's narrow phrase match (that one gates the write-gate
    and skill-body re-injection, which must stay strict; this one only affects
    model choice, so it can be broader)."""
    return bool(session and getattr(session, "_skill_explicit", False)
                and getattr(session, "_last_skill", None))


def _pick_model(skill, web, user_msg="", session=None, *, explicit=False):
    """Sonnet on explicit /skill, /web, or while an explicit-skill thread is
    still active. The active-thread check is deliberately broader than
    _continuation_allowed's fixed phrase list ("yes"/"save"/...): a natural
    clarifying-answer reply mid-skill (e.g. "the segment is small businesses")
    doesn't match that list, and without this it would silently drop to Haiku
    for one turn then jump back to Sonnet on the next "yes save" — a model
    switch pays the full uncached system-prompt cost twice instead of once.
    Only standalone read-only queries fall back to the cheap model."""
    if skill == "tokensave" and not web:
        return chat_session.CHAT_MODEL
    if web:
        return chat_session.ESCALATED_MODEL
    msg = (user_msg or "").strip()
    if skill and explicit:
        if _READ_TURN_RE.search(msg) and not _WRITE_TURN_RE.search(msg):
            return chat_session.CHAT_MODEL
        return chat_session.ESCALATED_MODEL
    if _in_active_skill_thread(session):
        if _READ_TURN_RE.search(msg) and not _WRITE_TURN_RE.search(msg) and not _CONTINUATION_RE.search(msg):
            return chat_session.CHAT_MODEL
        return chat_session.ESCALATED_MODEL
    return chat_session.CHAT_MODEL


def _tag_gate_message(suggest):
    skill = f"/{suggest}" if suggest else "/workspace or the skill for your task"
    return (
        f"Tag {skill} first (type / or tap ⊕ in the composer). "
        "Writes and GTM playbooks run on Sonnet only after you tag. "
        "Untagged turns stay on Haiku for reads and routing chat only."
    )


_SKILL_CONTINUATION = (
    "(continuing — full skill instructions are in session history; "
    "osctl get-project / read-file if state changed)"
)
_RESUME_NOTE = (
    "(resumed session — prior turns in context; "
    "osctl get-project / read-file for fresh detail)"
)


# Skills fully covered by CHAT_RAIL — inject stub only (avoids ~1k+ duplicate tok/turn).
_RAIL_COVERED_SKILL_STUBS: dict[str, str] = {
    "workspace": (
        "Tab map + write gate are in system prompt. Fill tabs: turn 1 = routing plan "
        "(sec01–sec06, one-line bullets, no osctl). Turn 2+ = one tab per osctl commit. "
        "Other intents: route per workspace skill table (venture-intake, product-build, etc.)."
    ),
}


def compose_turn_prompt(*, user_msg, context, skill, session, projects, suggest=None,
                        explicit=False, workspace=None):
    """Assemble one chat turn. Snapshot + full skill body only on fresh session."""
    parts = []
    fresh = session.is_fresh() if hasattr(session, "is_fresh") else not getattr(session, "_started", False)

    if fresh:
        try:
            parts.append(state_snapshot(projects))
        except Exception:  # noqa: BLE001
            pass
    else:
        parts.append(_RESUME_NOTE)

    if workspace:
        parts.append(workspace)

    if skill and explicit:
        last = getattr(session, "_last_skill", None)
        if fresh or skill != last:
            body_md = _load_skill_body(skill)
            if body_md:
                parts.append(f"## Active skill: {skill}\n{body_md}")
        else:
            parts.append(f"## Active skill: {skill}\n{_SKILL_CONTINUATION}")
    elif _continuation_allowed(session, user_msg):
        parts.append(f"## Active skill: {session._last_skill}\n{_SKILL_CONTINUATION}")
    elif suggest and not explicit:
        parts.append(
            f"## Skill hint (not active)\n"
            f"Wording suggests `{suggest}` — user did not tag. "
            f"Before any osctl write: tell them to add `/{suggest}` (⊕ picker). "
            "Reads ok; no commits this turn unless they tagged or this is a continuation."
        )

    if context:
        parts.append(context.strip())
    parts.append(f"## Request\n{user_msg}")
    return "\n\n".join(parts)


def _load_skill_body(name):
    """Read a routed skill's SKILL.md, returning its instruction body (frontmatter
    stripped). Returns '' if missing. Rail-covered skills return a short stub."""
    stub = _RAIL_COVERED_SKILL_STUBS.get(name)
    if stub:
        return stub
    f = SKILLS_DIR / name / "SKILL.md"
    if not f.exists():
        return ""
    txt = f.read_text(encoding="utf-8")
    # strip a leading YAML frontmatter block (--- ... ---)
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end != -1:
            txt = txt[end + 4:]
    return txt.strip()


def _skills_index():
    """List the OS skills (name + one-line description from SKILL.md frontmatter)
    for the chat's manual skill picker. Sorted by name."""
    out = []
    if not SKILLS_DIR.exists():
        return out
    for d in sorted(SKILLS_DIR.iterdir()):
        f = d / "SKILL.md"
        if not f.exists():
            continue
        fm, _ = fileops._parse_frontmatter(f.read_text(encoding="utf-8"))
        out.append({"name": fm.get("name", d.name),
                    "description": fm.get("description", "")})
    return out


_CHAT = None
_CHAT_SCOPE = None


def get_chat_session(project_scope=None, chat_id=None, new=False):
    """Return a session isolated to one project (or the unscoped dashboard).

    A Claude resume contains earlier prompts and tool results. Reusing it after
    switching linked projects would retain the previous app's evidence even
    though current filesystem permissions changed, so a scope change starts a
    fresh conversation (the old chat stays saved).

    `chat_id` reopens a saved chat (chat_store) when it is not the active one;
    `new` forces a fresh session (client has no chat yet, so it must never
    silently continue whichever chat the server happens to have active).
    """
    global _CHAT, _CHAT_SCOPE
    scope = project_scope or None
    if new:
        if _CHAT is not None:
            _CHAT.close()
        _CHAT = chat_session.ChatSession(repo_dir=str(ROOT), rail=RAIL)
        _CHAT_SCOPE = scope
        return _CHAT
    if chat_id and (_CHAT is None or getattr(_CHAT, "session_id", None) != chat_id):
        rec = chat_store.load(chat_id)
        rec_scope = tuple(rec["scope"]) if rec and rec.get("scope") else None
        if _CHAT is not None:
            _CHAT.close()
        # An unscoped chat never had app access, so it may adopt a project.
        _CHAT = (chat_session.ChatSession.restore(str(ROOT), RAIL, rec)
                 if rec and rec_scope in (scope, None)
                 else chat_session.ChatSession(repo_dir=str(ROOT), rail=RAIL))
        _CHAT_SCOPE = scope
        return _CHAT
    if chat_id and _CHAT is not None and _CHAT_SCOPE is None:
        _CHAT_SCOPE = scope  # active unscoped chat adopts its first project
    if _CHAT is None or _CHAT_SCOPE != scope:
        if _CHAT is not None:
            _CHAT.close()
        _CHAT = chat_session.ChatSession(repo_dir=str(ROOT), rail=RAIL)
        _CHAT_SCOPE = scope
    return _CHAT


class Handler(BaseHTTPRequestHandler):
    server_version = "myOS/1.0"

    def end_headers(self):
        self.send_header("Content-Security-Policy", (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self' ws://127.0.0.1:* "
            "ws://localhost:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        ))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    # -- helpers ----------------------------------------------------------- #
    def _send(self, code, body, ctype="application/json"):
        payload = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_JSON_BYTES:
            raise ValueError("request body too large")
        if not length:
            return {}
        content_type = self.headers.get("Content-Type", "application/json").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
        return body

    def _expected_origins(self):
        port = self.server.server_address[1]
        return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def _valid_host(self):
        # Tests construct a handler without a network peer; real HTTP handlers
        # always have client_address and must pass the checks below.
        if not hasattr(self, "client_address"):
            return True
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in {
            f"127.0.0.1:{port}", f"localhost:{port}",
        }

    def _valid_cookie(self):
        if not hasattr(self, "client_address"):
            return True
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except Exception:  # malformed cookies are simply unauthenticated
            return False
        value = jar.get(AUTH_COOKIE)
        return bool(value and hmac.compare_digest(value.value, AUTH_TOKEN))

    def _authorized(self, *, require_origin=False):
        if not self._valid_host() or not self._valid_cookie():
            return False
        if not hasattr(self, "client_address"):
            return True
        origin = self.headers.get("Origin", "")
        if require_origin and not origin:
            return False
        if origin and origin not in self._expected_origins():
            return False
        if self.headers.get("Sec-Fetch-Site", "") not in {"", "same-origin", "none"}:
            return False
        return True

    def _profile_hint(self, body=None):
        qs = parse_qs(urlparse(self.path).query)
        prof = (qs.get("profile") or qs.get("profile_slug") or [None])[0]
        if not prof and body:
            prof = body.get("profile") or body.get("profile_slug")
        return (prof or "").strip() or None

    def log_message(self, fmt, *args):
        sys.stderr.write("  [dash] " + (fmt % args) + "\n")

    # -- AI chat (drives a persistent guard-railed ChatSession via SSE) --- #
    def _handle_ask(self, body):
        messages = body.get("messages", [])
        if not messages or messages[-1].get("role") != "user":
            return self._send(400, {"error": "no user message"})
        user_msg = messages[-1]["content"]

        # Per-turn routing: explicit @/skill tags only (keyword → hint, not Sonnet).
        context = (body.get("context") or "").strip()
        explicit = _explicit_skill(user_msg)
        suggest = _suggest_skill(user_msg) if not explicit else None
        skill = explicit
        projects = db.tree()
        project_slug = str(body.get("project_slug") or "").strip()
        project_record = next(
            (p for p in projects if p.get("slug") == project_slug), None,
        )
        project_scope = (
            (project_slug, project_record.get("local_folder") or "")
            if project_record else None
        )
        chat_id = body.get("chat_id") or None
        sess = get_chat_session(project_scope, chat_id, new=not chat_id)

        if (_WRITE_TURN_RE.search(user_msg or "")
                and not explicit
                and not _continuation_allowed(sess, user_msg)):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            gate = _tag_gate_message(suggest)
            self.wfile.write(f"data: {json.dumps({'delta': gate})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.log_message(
                "chat tag-gate suggest=%s turn=%d", suggest or "-", sess._turn_count,
            )
            return

        with_web = _needs_web(user_msg, skill)
        model = _pick_model(skill, with_web, user_msg, sess, explicit=bool(explicit))

        wants_file_search = _needs_workspace(user_msg, skill)
        wants_app_context = _needs_app_context(user_msg, skill, suggest)
        # A linked app is product context for the whole project—not only code
        # questions. Retrieval runs here exactly once; the model never receives
        # permission to invoke TokenSave itself.
        workspace_dir = resolve_linked_workspace(projects, project_slug)
        if skill == "tokensave" and not workspace_dir:
            # Deterministic zero-model response: do not inject a skill body or
            # spend a model turn when the requested graph has no safe target.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            message = (
                "Link an existing local app folder to the active myOS project "
                "first, then use /tokensave again."
            )
            self.wfile.write(f"data: {json.dumps({'delta': message})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.log_message("chat tokensave skipped: no active linked folder")
            return
        tokensave_task = re.sub(
            r"(?i)(?:^|\s)[@/]tokensave\b", " ", user_msg,
        ).replace("\x00", "").strip()[:tokensave_bridge.MAX_QUERY_CHARS]
        if not tokensave_task:
            tokensave_task = "Summarize this app's product, users, and main capabilities"

        tokensave_ready = tokensave_index_ready(workspace_dir)
        if skill == "tokensave" and not tokensave_ready:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            message = (
                "The linked app has no TokenSave index yet. Run `tokensave init` "
                "once inside that app folder, then use /tokensave again. No model "
                "turn was spent."
            )
            self.wfile.write(f"data: {json.dumps({'delta': message})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.log_message("chat tokensave skipped: linked folder has no index")
            return

        graph_context = ""
        graph_error = None
        if workspace_dir and wants_app_context and tokensave_ready:
            try:
                graph_context = tokensave_bridge.context(
                    project_slug, tokensave_task, active_project=project_slug,
                )
            except (tokensave_bridge.BridgeError, OSError) as exc:
                graph_error = str(exc)[:1200]

        if skill == "tokensave" and graph_error:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            message = (
                f"TokenSave could not refresh the linked app: {graph_error}. "
                "No stale context was used and no model turn was spent."
            )
            self.wfile.write(f"data: {json.dumps({'delta': message})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.log_message("chat tokensave skipped: refresh failed")
            return

        file_search_mode = bool(
            workspace_dir
            and (wants_file_search
                 or (wants_app_context and not graph_context))
        )
        workspace = ""
        if workspace_dir and (wants_app_context or file_search_mode):
            workspace = linked_workspace_prompt(
                project_slug, workspace_dir, graph_context=graph_context,
                graph_error=graph_error, file_search_mode=file_search_mode,
            )
        if wants_file_search and project_slug and not workspace_dir:
            workspace = (
                "## App workspace unavailable\n"
                "The requested project's local-folder link is missing, stale, or "
                "invalid. Do not inspect the myOS source tree as a substitute; "
                "ask the user to relink the app folder."
            )

        text = compose_turn_prompt(
            user_msg=user_msg,
            context=context,
            skill=skill,
            session=sess,
            projects=projects,
            suggest=suggest,
            explicit=bool(explicit),
            workspace=workspace,
        )
        sess.note_skill(skill, explicit=bool(explicit))

        ctx_len = len((body.get("context") or "").strip())
        fresh = sess.is_fresh()
        self.log_message(
            "chat turn prompt=%d ctx=%d skill=%s explicit=%s model=%s web=%s app=%s graph=%s files=%s fresh=%s turn=%d",
            len(text), ctx_len, skill or "-", bool(explicit), model, with_web,
            bool(workspace_dir), bool(graph_context), file_search_mode, fresh,
            sess._turn_count,
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        reply = []
        try:
            # Tell the client which saved chat this turn belongs to (a scope
            # change or first turn may have started a new one).
            if isinstance(getattr(sess, "session_id", None), str):
                saved = chat_store.load(sess.session_id)
                emit({"chat_id": sess.session_id,
                      "title": (saved or {}).get("title") or chat_store.title_from(user_msg),
                      "project": project_scope[0] if project_scope else None})
            for kind, payload in sess.ask(
                    text, with_web=with_web, model=model,
                    workspace_dir=(workspace_dir if file_search_mode else None),
                    file_search_mode=file_search_mode):
                if kind == "delta":
                    reply.append(payload)
                    emit({"delta": payload})
                elif kind == "tool":
                    emit({"tool": payload})
                elif kind == "error":
                    emit({"error": payload})
                # "done" → fall through to [DONE]
        except (BrokenPipeError, ConnectionResetError):
            pass  # client stopped/closed; still save what streamed so far
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            emit({"error": "internal error"})
        finally:
            if isinstance(getattr(sess, "session_id", None), str):
                try:
                    chat_store.record_turn(sess, project_scope, user_msg, "".join(reply))
                except (OSError, ValueError):
                    traceback.print_exc()
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    # -- integrated terminal (full-trust claude over a PTY/WebSocket) ------ #
    def _handle_terminal_ws(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._send(400, {"error": "missing Sec-WebSocket-Key"})
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", ws.accept_key(key))
        self.end_headers()

        sock = self.connection
        lock = threading.Lock()

        def on_output(chunk):
            with lock:
                try:
                    sock.sendall(ws.encode_frame(chunk, ws.OP_BIN))
                except OSError:
                    pass

        term = terminal_session.TerminalSession(cmd=["claude"], cwd=str(ROOT))
        term.start(on_output)

        buf = b""
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while True:
                    opcode, payload, consumed = ws.decode_frame(
                        buf, max_payload=MAX_WS_PAYLOAD, require_masked=True,
                    )
                    if opcode is None:
                        break
                    buf = buf[consumed:]
                    if opcode == ws.OP_CLOSE:
                        raise ConnectionError
                    if opcode == ws.OP_PING:
                        with lock:
                            sock.sendall(ws.encode_frame(payload, ws.OP_PONG))
                        continue
                    # Control message (resize) vs keystrokes
                    handled = False
                    if opcode == ws.OP_TEXT:
                        try:
                            msg = json.loads(payload.decode())
                            if isinstance(msg, dict) and msg.get("type") == "resize":
                                term.resize(int(msg["cols"]), int(msg["rows"]))
                                handled = True
                        except (ValueError, KeyError):
                            handled = False
                    if not handled:
                        term.write(payload)
        except (OSError, ConnectionError, ValueError):
            pass
        finally:
            term.close()

    # -- GET --------------------------------------------------------------- #
    def do_GET(self):
        path = urlparse(self.path).path
        if not self._valid_host():
            return self._send(403, {"error": "forbidden"})
        if path == "/ws/terminal" and self.headers.get("Upgrade", "").lower() == "websocket":
            if not self._authorized(require_origin=True):
                return self._send(403, {"error": "forbidden"})
            return self._handle_terminal_ws()
        if path in ("/", "/index.html"):
            # no-store on the shell too: it embeds ?v=<mtime> asset URLs, so if the
            # webview caches app.html it keeps loading stale CSS/JS forever. Always
            # re-fetch the shell so UI updates actually reach the user.
            data = _app_html_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Set-Cookie",
                f"{AUTH_COOKIE}={AUTH_TOKEN}; HttpOnly; SameSite=Strict; Path=/",
            )
            self.end_headers()
            self.wfile.write(data)
            return

        if path in ("/ui-tokens.css", "/app.css", "/app.js", "/os-ids.js", "/post-copy.js", "/logo.svg"):
            f = HERE / path.lstrip("/")
            ctype = (
                "text/css" if path.endswith(".css")
                else "image/svg+xml" if path.endswith(".svg")
                else "application/javascript"
            )
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path.startswith("/vendor/"):
            f = (HERE / path.lstrip("/")).resolve()
            if f.is_file() and f.is_relative_to((HERE / "vendor").resolve()):
                ctype = "text/css" if f.suffix == ".css" else "application/javascript"
                return self._send(200, f.read_bytes(), ctype)
            return self._send(404, {"error": "not found"})

        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._authorized():
            return self._send(403, {"error": "forbidden"})
        if not db.db_exists():
            return self._send(503, {"error": "os.db not found — run index.py first"})

        try:
            if path == "/api/chat-session":
                if _CHAT is None:
                    return self._send(200, {"session_id": None, "turn_count": 0, "fresh": True})
                return self._send(200, _CHAT.session_meta())
            if path == "/api/chats":
                return self._send(200, {"chats": chat_store.list_meta()})
            if path.startswith("/api/chats/"):
                rec = chat_store.load(path[len("/api/chats/"):])
                if rec is None:
                    return self._send(404, {"error": "chat not found"})
                return self._send(200, rec)
            if path == "/api/timeline":
                return self._send(200, db.timeline())
            if path == "/api/tree":
                return self._send(200, db.tree())
            if path == "/api/posts-index":
                return self._send(200, db.posts())
            if path == "/api/skills-index":
                return self._send(200, _skills_index())
            if path == "/api/schemas":
                return self._send(200, schemas_for_api())
            if path == "/api/id-catalog":
                tree = db.tree()
                entries = build_catalog(tree, root=ROOT, posts=db.posts())
                return self._send(200, {"entries": entries, "count": len(entries)})
            if path == "/api/id-registry":
                tree = db.tree()
                feats = db._rows("SELECT product_slug, title, status FROM features ORDER BY product_slug, title")
                reg = build_id_registry(tree, db.posts(), root=ROOT, features=feats)
                return self._send(200, {"lookup": reg.lookup, "entries": reg.entries, "count": len(reg.entries)})
            if path.startswith("/api/project/"):
                slug = path[len("/api/project/"):]
                data = db.project(slug)
                if data is None:
                    return self._send(404, {"error": f"project '{slug}' not found"})
                for m in data["memos"]:
                    m["body"] = fileops.read_authored_json(m.get("file_path"))
                for x in data["experiments"]:
                    x["body"] = fileops.read_authored_json(x.get("file_path"))
                tree = db.tree()
                reg = build_id_registry(tree, db.posts(), root=ROOT, features=data["features"])
                data["memos"] = fileops.enrich_project_memos(data["memos"], slug, reg)
                data["experiments"] = fileops.enrich_project_experiments(data["experiments"], slug, reg)
                data["features"] = fileops.enrich_project_features(data["features"], reg)
                data["sections"] = build_project_sections(slug, ROOT, data, registry=reg)
                from core import gtm as _gtm
                data["gtm"] = _gtm.build_view(ROOT, slug, reg, data["experiments"])
                data["subsection_ids"] = subsection_id_map(reg, slug)
                from core.project_schemas import feature_form_fields

                data["subsections"] = fileops.read_subsections(slug)
                data["feature"] = feature_form_fields(data["subsections"]["docs"]["roadmap"])
                return self._send(200, data)
            if path.startswith("/api/profile/") and path.endswith("/posts"):
                slug = path[len("/api/profile/"):-len("/posts")]
                return self._send(200, db.profile_posts(slug))
            if path.startswith("/api/profile/") and path.endswith("/platforms"):
                slug = path[len("/api/profile/"):-len("/platforms")]
                return self._send(200, {"platforms": fileops.profile_platforms(slug)})
            if path.startswith("/api/profile/"):
                for seg, cfg in _ARTIFACT_ROUTES.items():
                    if path.endswith(f"/{seg}"):
                        slug = path[len("/api/profile/"):-len(f"/{seg}")]
                        return self._send(200, {cfg["list_key"]: cfg["list"](slug)})
                    if f"/{seg}/" in path:
                        slug, art_id = path[len("/api/profile/"):].split(f"/{seg}/", 1)
                        return self._send(200, cfg["get"](slug, art_id))
            if path.startswith("/api/profile/"):
                slug = path[len("/api/profile/"):]
                return self._send(200, fileops.read_profile(slug))
            if path.startswith("/api/channel/") and path.endswith("/guidelines"):
                slug = path[len("/api/channel/"):-len("/guidelines")]
                return self._send(200, {"text": fileops.read_channel_guidelines(slug)})
            if path.startswith("/api/post/"):
                post_id = path[len("/api/post/"):]
                return self._send(200, fileops.read_detail(post_id, self._profile_hint()))
        except fileops.ActionError as exc:
            return self._send(404, {"error": str(exc)})
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": "internal error"})
        return self._send(404, {"error": "unknown endpoint"})

    # -- POST (mutations: file write + re-index) --------------------------- #
    def do_POST(self):
        global _CHAT, _CHAT_SCOPE
        path = urlparse(self.path).path
        if not self._authorized():
            return self._send(403, {"error": "forbidden"})
        try:
            body = self._read_json()
            if path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
                return
            if path.startswith("/api/profile/") and path.endswith("/posts"):
                slug = path[len("/api/profile/"):-len("/posts")]
                return self._send(200, {"ok": True, **fileops.add_post(slug, body)})
            # brief-specs/voices routes must be checked before the generic profile
            # /update and /delete below — those match ANY /api/profile/.../update
            # or .../delete path, which would otherwise swallow these nested ones.
            if path.startswith("/api/profile/"):
                for seg, cfg in _ARTIFACT_ROUTES.items():
                    if f"/{seg}/" in path and path.endswith("/update"):
                        rest = path[len("/api/profile/"):-len("/update")]
                        slug, art_id = rest.rstrip("/").split(f"/{seg}/", 1)
                        text = body.get("text", "")
                        platforms = body.get("platforms")
                        return self._send(200, {"ok": True, **cfg["update"](slug, text, art_id, platforms)})
                    if f"/{seg}/" in path and path.endswith("/delete"):
                        rest = path[len("/api/profile/"):-len("/delete")]
                        slug, art_id = rest.rstrip("/").split(f"/{seg}/", 1)
                        return self._send(200, cfg["delete"](slug, art_id))
                    if path.endswith(f"/{seg}"):
                        slug = path[len("/api/profile/"):-len(f"/{seg}")]
                        text = body.get("text", "")
                        platforms = body.get("platforms", "all")
                        return self._send(200, {"ok": True, **cfg["create"](slug, text, platforms)})
            if path.startswith("/api/profile/") and path.endswith("/update"):
                slug = path[len("/api/profile/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_profile(slug, body)})
            if path.startswith("/api/profile/") and path.endswith("/brief-spec"):
                # legacy single-spec path — kept so any not-yet-updated caller still
                # hits br1 rather than 404ing.
                slug = path[len("/api/profile/"):-len("/brief-spec")]
                text = body.get("text")
                if text is None:
                    text = body.get("brief_spec", "")
                return self._send(200, {"ok": True, **fileops.write_brief_spec(slug, text)})
            if path.startswith("/api/profile/") and path.endswith("/plan"):
                slug = path[len("/api/profile/"):-len("/plan")]
                return self._send(200, {"ok": True, **fileops.run_plan(slug, body)})
            if path.startswith("/api/post/") and path.endswith("/update"):
                post_id = path[len("/api/post/"):-len("/update")]
                prof = self._profile_hint(body)
                return self._send(200, {"ok": True, **fileops.update_post(post_id, body, prof)})
            if path == "/api/posts/delete":
                return self._send(200, {"ok": True, **fileops.delete_posts(
                    body.get("ids", []), self._profile_hint(body))})
            if path.startswith("/api/post/") and path.endswith("/delete"):
                post_id = path[len("/api/post/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_post(
                    post_id, self._profile_hint(body))})
            if path.startswith("/api/post/") and path.endswith("/status"):
                post_id = path[len("/api/post/"):-len("/status")]
                result = fileops.set_status(
                    post_id, body.get("status"), self._profile_hint(body))
                return self._send(200, {"ok": True, **result})
            if path.startswith("/api/post/") and path.endswith("/brief"):
                post_id = path[len("/api/post/"):-len("/brief")]
                result = fileops.generate_brief(post_id, profile_slug=self._profile_hint(body))
                return self._send(200, {"ok": True, **result})
            if path.startswith("/api/post/") and path.endswith("/slide/new"):
                post_id = path[len("/api/post/"):-len("/slide/new")]
                return self._send(200, {"ok": True, **fileops.add_slide_overlay(
                    post_id, body.get("overlay", ""), self._profile_hint(body))})
            if path.startswith("/api/post/") and path.endswith("/revise"):
                post_id = path[len("/api/post/"):-len("/revise")]
                result = fileops.revise_post(
                    post_id, body.get("instruction", ""), self._profile_hint(body))
                return self._send(200, {"ok": True, **result})
            if path.startswith("/api/channel/") and path.endswith("/guidelines/refine"):
                slug = path[len("/api/channel/"):-len("/guidelines/refine")]
                return self._send(200, {"ok": True, **fileops.refine_guidelines(slug, body.get("text", ""))})
            if path.startswith("/api/channel/") and path.endswith("/guidelines"):
                slug = path[len("/api/channel/"):-len("/guidelines")]
                return self._send(200, {"ok": True, **fileops.write_channel_guidelines(slug, body.get("text", ""))})
            if path.startswith("/api/channel/") and path.endswith("/update"):
                slug = path[len("/api/channel/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_channel(slug, body)})
            if path.startswith("/api/channel/") and path.endswith("/delete"):
                slug = path[len("/api/channel/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_channel(slug)})
            if path.startswith("/api/profile/") and path.endswith("/delete"):
                slug = path[len("/api/profile/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_profile(slug)})
            if path == "/api/activity/delete":
                return self._send(200, {"ok": True, **fileops.delete_activity(body.get("title", ""))})
            if path == "/api/local-folder/pick":
                return self._send(200, {"ok": True, **pick_local_folder()})
            if path == "/api/project/new":
                slug = (body.get("slug") or fileops._slugify(body.get("name", ""))).strip()
                return self._send(200, {"ok": True, **fileops.create_project(slug, body)})
            # memo/experiment update+delete must be checked before the generic
            # project update/delete below — both match ANY /api/project/.../update
            # or .../delete path, which would otherwise swallow these nested ones.
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
            # GTM (sec07): phases + strategies. Specific routes before generic /update.
            if path.startswith("/api/project/") and path.endswith("/phase/new"):
                proj = path[len("/api/project/"):-len("/phase/new")]
                return self._send(200, {"ok": True, **fileops.create_phase(
                    proj, body.get("name", ""), body.get("goal", ""),
                    body.get("timebox", ""), body.get("status", "planned"))})
            if path.startswith("/api/project/") and "/phase/" in path and path.endswith("/update"):
                rest = path[len("/api/project/"):-len("/update")]
                proj, tail = rest.split("/phase/", 1)
                return self._send(200, {"ok": True, **fileops.update_phase(proj, tail.rstrip("/"), body)})
            if path.startswith("/api/project/") and "/phase/" in path and path.endswith("/delete"):
                rest = path[len("/api/project/"):-len("/delete")]
                proj, tail = rest.split("/phase/", 1)
                return self._send(200, {"ok": True, **fileops.delete_phase(proj, tail.rstrip("/"))})
            if path.startswith("/api/project/") and path.endswith("/strategy/new"):
                proj = path[len("/api/project/"):-len("/strategy/new")]
                return self._send(200, {"ok": True, **fileops.create_strategy(
                    proj, body.get("phase", ""), body.get("channel", ""),
                    body.get("hypothesis", ""), body.get("name", ""), bool(body.get("primary")))})
            if path.startswith("/api/project/") and "/strategy/" in path and path.endswith("/update"):
                rest = path[len("/api/project/"):-len("/update")]
                proj, tail = rest.split("/strategy/", 1)
                return self._send(200, {"ok": True, **fileops.update_strategy(proj, tail.rstrip("/"), body)})
            if path.startswith("/api/project/") and "/strategy/" in path and path.endswith("/delete"):
                rest = path[len("/api/project/"):-len("/delete")]
                proj, tail = rest.split("/strategy/", 1)
                return self._send(200, {"ok": True, **fileops.delete_strategy(proj, tail.rstrip("/"))})
            if path.startswith("/api/project/") and path.endswith("/folder/open"):
                slug = path[len("/api/project/"):-len("/folder/open")]
                folder = fileops.project_local_folder(slug)
                open_local_folder(folder)
                return self._send(200, {"ok": True, "path": folder})
            if path.startswith("/api/project/") and path.endswith("/update"):
                slug = path[len("/api/project/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_project(slug, body)})
            if path.startswith("/api/project/") and path.endswith("/delete"):
                slug = path[len("/api/project/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_project(slug)})
            if path.startswith("/api/project/") and path.endswith("/intake/new"):
                proj = path[len("/api/project/"):-len("/intake/new")]
                return self._send(200, {"ok": True, **fileops.create_intake(proj)})
            if path.startswith("/api/project/") and path.endswith("/technical/new"):
                proj = path[len("/api/project/"):-len("/technical/new")]
                return self._send(200, {"ok": True, **fileops.create_technical(proj)})
            if path.startswith("/api/project/") and path.endswith("/subsections/update"):
                proj = path[len("/api/project/"):-len("/subsections/update")]
                doc = (body.get("doc") or "").strip()
                titles = body.get("subsections") or body.get("titles") or []
                if isinstance(titles, str):
                    titles = fileops.parse_subsections_arg(titles)
                if not doc or doc not in ("intake", "technical", "roadmap"):
                    return self._send(400, {"error": "doc must be intake, technical, or roadmap"})
                if not titles:
                    return self._send(400, {"error": "subsections list required"})
                return self._send(200, {"ok": True, **fileops.update_subsections(proj, doc, titles)})
            if path.startswith("/api/project/") and path.endswith("/subsections/add"):
                proj = path[len("/api/project/"):-len("/subsections/add")]
                doc = (body.get("doc") or "").strip()
                title = (body.get("title") or "").strip()
                if not doc or doc not in ("intake", "technical", "roadmap"):
                    return self._send(400, {"error": "doc must be intake, technical, or roadmap"})
                if not title:
                    return self._send(400, {"error": "title required"})
                return self._send(200, {"ok": True, **fileops.add_subsection(proj, doc, title)})
            if "/doc/" in path and path.endswith("/section"):
                # /api/project/<slug>/doc/<intake|technical>/section
                rest = path[len("/api/project/"):-len("/section")]
                parts = rest.split("/doc/")
                if len(parts) != 2:
                    return self._send(400, {"error": "bad doc section path"})
                proj, doc = parts[0].strip("/"), parts[1].strip("/")
                title = (body.get("title") or "").strip()
                text = body.get("body")
                if text is None:
                    text = body.get("text", "")
                if not title:
                    return self._send(400, {"error": "title required"})
                return self._send(200, {"ok": True,
                                        **fileops.update_doc_section(proj, doc, title, text)})
            if path.startswith("/api/project/") and path.endswith("/validation-tab/update"):
                proj = path[len("/api/project/"):-len("/validation-tab/update")]
                titles = body.get("subsections") or body.get("titles") or []
                if isinstance(titles, str):
                    titles = fileops.parse_subsections_arg(titles)
                if not titles:
                    return self._send(400, {"error": "subsections list required"})
                return self._send(200, {"ok": True, **fileops.update_validation_tab(proj, titles)})
            if path.startswith("/api/project/") and path.endswith("/memo/new"):
                proj = path[len("/api/project/"):-len("/memo/new")]
                mtype = (body.get("type") or "").strip()
                return self._send(200, {"ok": True, **fileops.create_memo(proj, mtype, body)})
            if path.startswith("/api/project/") and path.endswith("/experiment/new"):
                proj = path[len("/api/project/"):-len("/experiment/new")]
                return self._send(200, {"ok": True, **fileops.create_experiment(proj, body)})
            if path.startswith("/api/project/") and path.endswith("/product/new"):
                proj = path[len("/api/project/"):-len("/product/new")]
                slug = (body.get("slug") or fileops._slugify(body.get("name", ""))).strip()
                return self._send(200, {"ok": True, **fileops.create_product(proj, slug, body)})
            if path.startswith("/api/product/") and path.endswith("/feature/new"):
                prod_slug = path[len("/api/product/"):-len("/feature/new")]
                return self._send(200, {"ok": True, **fileops.add_feature(prod_slug, body)})
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
            if path.startswith("/api/project/") and path.endswith("/profile/new"):
                proj = path[len("/api/project/"):-len("/profile/new")]
                slug = (body.get("slug") or fileops._slugify(body.get("name", ""))).strip()
                return self._send(200, {"ok": True, **fileops.create_profile(proj, slug, body)})
            if path.startswith("/api/profile/") and path.endswith("/channel/new"):
                prof = path[len("/api/profile/"):-len("/channel/new")]
                slug = (body.get("slug") or fileops._slugify(body.get("platform", ""))).strip()
                return self._send(200, {"ok": True, **fileops.create_channel(prof, slug, body.get("platform",""), body.get("handle",""))})
            if path == "/api/activity/new":
                return self._send(200, {"ok": True, **fileops.create_activity(body)})
            if path == "/api/activity/done":
                return self._send(200, {"ok": True, **fileops.mark_activity_done(body.get("title",""), body.get("entity",""))})
            if path == "/api/milestone/new":
                return self._send(200, {"ok": True, **fileops.create_milestone(body)})
            if path.startswith("/api/milestone/") and path.endswith("/update"):
                ms_id = path[len("/api/milestone/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_milestone(ms_id, body)})
            if path.startswith("/api/milestone/") and path.endswith("/delete"):
                ms_id = path[len("/api/milestone/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_milestone(ms_id)})
            if path == "/api/ask":
                return self._handle_ask(body)
            if path == "/api/upload-temp":
                encoded = body.get("data", "")
                if not isinstance(encoded, str):
                    raise ValueError("upload data must be base64 text")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("invalid base64 upload") from exc
                if len(data) > MAX_UPLOAD_BYTES:
                    raise ValueError("upload too large")
                ext = (body.get("ext", "png") or "png").lstrip(".").lower()
                if ext not in UPLOAD_EXTENSIONS:
                    raise ValueError("unsupported upload type")
                fd, fpath = tempfile.mkstemp(suffix=f".{ext}", prefix="workspace_img_")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                return self._send(200, {"path": fpath})
            if path == "/api/chat-stop":
                # Abort the in-flight turn (kills the claude subprocess so it
                # stops consuming tokens) but KEEP the session so the next
                # message resumes the same context. Unlike chat-reset.
                if _CHAT is not None:
                    _CHAT.close()
                return self._send(200, {"ok": True})
            if path == "/api/chat-reset":
                # New chat: drop the active session; saved chats are untouched.
                if _CHAT is not None:
                    _CHAT.close()
                    _CHAT = None
                    _CHAT_SCOPE = None
                return self._send(200, {"ok": True})
            if path.startswith("/api/chats/") and path.endswith("/delete"):
                chat_id = path[len("/api/chats/"):-len("/delete")]
                if _CHAT is not None and getattr(_CHAT, "session_id", None) == chat_id:
                    _CHAT.close()
                    _CHAT = None
                    _CHAT_SCOPE = None
                return self._send(200, {"ok": chat_store.delete(chat_id)})
        except fileops.ActionError as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except (TypeError, ValueError) as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": "internal error"})
        return self._send(404, {"error": "unknown endpoint"})


def main():
    # Line-buffer stdout/stderr so the startup banner + request log reach
    # server.log immediately (anaconda python block-buffers a redirected stdout,
    # which otherwise makes the log look empty/stale while the server runs).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-reindex", action="store_true", help="skip the startup re-index")
    args = ap.parse_args()

    if not args.no_reindex:
        print("Re-indexing os.db from source files...")
        r = subprocess.run([sys.executable, str(ROOT / "index.py"), str(ROOT)],
                           capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            sys.exit("startup re-index failed — fix source files and retry")

    def _shutdown_children(*_a):
        # Terminate the chat agent's in-flight turn, if any. Per-connection
        # TerminalSessions already close() in _handle_terminal_ws's finally.
        if _CHAT is not None:
            try:
                _CHAT.close()
            except Exception:  # noqa: BLE001
                pass

    # /api/quit raises SIGTERM on this PID; clean up children before exiting.
    signal.signal(signal.SIGTERM, lambda *a: (_shutdown_children(), sys.exit(0)))

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\nmyOS dashboard → http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        _shutdown_children()


if __name__ == "__main__":
    main()
