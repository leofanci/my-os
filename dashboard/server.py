#!/usr/bin/env python3
"""server.py — the thin local dashboard for the GTM OS.

Architecture (locked): Python stdlib http.server, a clean JSON API over READ-side
db.py and WRITE-side fileops.py, serving a single static app.html. Reads come from
os.db (read-only); writes mutate FILES then re-index. The dashboard never writes
os.db directly. This is 'server-shaped' on purpose — porting to a real server is
add-an-ASGI-host + auth, no rewrite.

Run:  python3 dashboard/server.py [--port 8765]
"""

import argparse
import base64
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
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

RAIL = CHAT_RAIL


def _app_html_bytes() -> bytes:
    """Serve app.html with cache-busted asset URLs (mtime) so UI updates land."""
    html = APP_HTML.read_text(encoding="utf-8")
    for name in ("app.css", "app.js", "os-ids.js"):
        v = int((HERE / name).stat().st_mtime)
        html = html.replace(f"/{name}\"", f"/{name}?v={v}\"")
    return html.encode("utf-8")


def state_snapshot(projects):
    """COMPACT OS index for the chat agent — projects/profiles/channels plus
    per-entity counts, NOT full content. Bounded in size as content grows (the
    old version enumerated every post/memo/activity every turn). The agent pulls
    detail on demand via osctl get-posts / get-project / read-file."""
    lines = ["## Current GTM OS state",
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
SKILLS_DIR = ROOT / ".claude" / "skills"

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
    ("gtm-os",             r"fill.{0,40}\btabs?\b|fill.{0,40}\bpanel\b|left panel|project sections?|divide.{0,50}\btabs?\b|populate.{0,40}(tabs?|panel|sections?)"),
    ("product-build",      r"product roadmap|build status|feature roadmap|plan (the )?features"),
    ("gtm-assessment",     r"assess\w*|where (do|does) (we|this) stand|pace call|gtm assessment"),
    # gtm-os is the catch-all dispatcher for strategic asks that matched nothing
    # specific — handled separately in _route_skill so it has lowest priority.
]
SKILL_NAMES = frozenset(name for name, _ in _SKILL_ROUTES) | {"gtm-os"}
_COMPILED_ROUTES = [(name, re.compile(pat, re.I)) for name, pat in _SKILL_ROUTES]
_MENTION_RE = re.compile(r"[@/]([a-z][a-z0-9-]+)")
# Generic strategic intent with no specific skill → route to the gtm-os dispatcher.
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


def _pick_model(skill, web, user_msg="", session=None, *, explicit=False):
    """Sonnet only on explicit /skill, /web, or tagged-thread continuations."""
    if web:
        return chat_session.ESCALATED_MODEL
    if skill and explicit:
        msg = (user_msg or "").strip()
        if _READ_TURN_RE.search(msg) and not _WRITE_TURN_RE.search(msg):
            return chat_session.CHAT_MODEL
        return chat_session.ESCALATED_MODEL
    if session and _continuation_allowed(session, user_msg):
        return chat_session.ESCALATED_MODEL
    return chat_session.CHAT_MODEL


def _tag_gate_message(suggest):
    skill = f"/{suggest}" if suggest else "/gtm-os or the skill for your task"
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
    "gtm-os": (
        "Tab map + write gate are in system prompt. Fill tabs: turn 1 = routing plan "
        "(sec01–sec06, one-line bullets, no osctl). Turn 2+ = one tab per osctl commit. "
        "Other intents: route per gtm-os skill table (venture-intake, product-build, etc.)."
    ),
}


def compose_turn_prompt(*, user_msg, context, skill, session, projects, suggest=None, explicit=False):
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


def get_chat_session():
    global _CHAT
    if _CHAT is None:
        _CHAT = chat_session.ChatSession(repo_dir=str(ROOT), rail=RAIL)
    return _CHAT


class Handler(BaseHTTPRequestHandler):
    server_version = "GTMOS-Dashboard/1.0"

    # -- helpers ----------------------------------------------------------- #
    def _send(self, code, body, ctype="application/json"):
        payload = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

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
        sess = get_chat_session()

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

        text = compose_turn_prompt(
            user_msg=user_msg,
            context=context,
            skill=skill,
            session=sess,
            projects=db.tree(),
            suggest=suggest,
            explicit=bool(explicit),
        )
        sess.note_skill(skill, explicit=bool(explicit))

        ctx_len = len((body.get("context") or "").strip())
        fresh = sess.is_fresh()
        self.log_message(
            "chat turn prompt=%d ctx=%d skill=%s explicit=%s model=%s web=%s fresh=%s turn=%d",
            len(text), ctx_len, skill or "-", bool(explicit), model, with_web, fresh,
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

        try:
            for kind, payload in get_chat_session().ask(text, with_web=with_web, model=model):
                if kind == "delta":
                    emit({"delta": payload})
                elif kind == "tool":
                    emit({"tool": payload})
                elif kind == "error":
                    emit({"error": payload})
                # "done" → fall through to [DONE]
        except Exception as exc:  # noqa: BLE001
            emit({"error": repr(exc)})
        finally:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

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
                    opcode, payload, consumed = ws.decode_frame(buf)
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
        except (OSError, ConnectionError):
            pass
        finally:
            term.close()

    # -- GET --------------------------------------------------------------- #
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/ws/terminal" and self.headers.get("Upgrade", "").lower() == "websocket":
            return self._handle_terminal_ws()
        if path in ("/", "/index.html"):
            return self._send(200, _app_html_bytes(), "text/html; charset=utf-8")

        if path == "/quit":
            self._send(200, {"ok": True})
            threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
            return

        if path in ("/app.css", "/app.js", "/os-ids.js"):
            f = HERE / path.lstrip("/")
            ctype = "text/css" if path.endswith(".css") else "application/javascript"
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
            if f.is_file() and str(f).startswith(str(HERE / "vendor")):
                ctype = "text/css" if f.suffix == ".css" else "application/javascript"
                return self._send(200, f.read_bytes(), ctype)
            return self._send(404, {"error": "not found"})

        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not db.db_exists():
            return self._send(503, {"error": "os.db not found — run index.py first"})

        try:
            if path == "/api/chat-session":
                if _CHAT is None:
                    return self._send(200, {"session_id": None, "turn_count": 0,
                                            "max_turns": chat_session.MAX_TURNS, "fresh": True})
                return self._send(200, _CHAT.session_meta())
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
                data["subsection_ids"] = subsection_id_map(reg, slug)
                from core.project_schemas import feature_form_fields

                data["subsections"] = fileops.read_subsections(slug)
                data["feature"] = feature_form_fields(data["subsections"]["docs"]["roadmap"])
                return self._send(200, data)
            if path.startswith("/api/profile/") and path.endswith("/posts"):
                slug = path[len("/api/profile/"):-len("/posts")]
                return self._send(200, db.profile_posts(slug))
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
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": repr(exc)})
        return self._send(404, {"error": "unknown endpoint"})

    # -- POST (mutations: file write + re-index) --------------------------- #
    def do_POST(self):
        global _CHAT
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path.startswith("/api/profile/") and path.endswith("/posts"):
                slug = path[len("/api/profile/"):-len("/posts")]
                return self._send(200, {"ok": True, **fileops.add_post(slug, body)})
            if path.startswith("/api/profile/") and path.endswith("/update"):
                slug = path[len("/api/profile/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_profile(slug, body)})
            if path.startswith("/api/profile/") and path.endswith("/brief-spec"):
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
            if path == "/api/project/new":
                slug = (body.get("slug") or fileops._slugify(body.get("name", ""))).strip()
                return self._send(200, {"ok": True, **fileops.create_project(slug, body)})
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
                data = base64.b64decode(body.get("data", ""))
                ext = (body.get("ext", "png") or "png").lstrip(".")
                fd, fpath = tempfile.mkstemp(suffix=f".{ext}", prefix="gtmos_img_")
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
                if _CHAT is not None:
                    _CHAT.close()
                    _CHAT = None
                return self._send(200, {"ok": True})
        except fileops.ActionError as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": repr(exc)})
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

    # /quit raises SIGTERM on this PID; clean up children before exiting.
    signal.signal(signal.SIGTERM, lambda *a: (_shutdown_children(), sys.exit(0)))

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\nGTM OS dashboard → http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        _shutdown_children()


if __name__ == "__main__":
    main()
