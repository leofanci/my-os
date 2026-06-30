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
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import db                # noqa: E402
import fileops           # noqa: E402
import chat_session      # noqa: E402
import ws                # noqa: E402
import terminal_session  # noqa: E402

APP_HTML = HERE / "app.html"

RAIL = (
    "You are the GTM OS dashboard chat assistant. "
    "You operate a GTM OS whose source of truth is authored files. "
    "Mutate state ONLY by running `python3 -m dashboard.osctl <command>` "
    "(e.g. create-project, create-profile, create-channel, add-post, "
    "create-activity, create-milestone, mark-done, update-post, set-status, "
    "update-project, update-channel, update-milestone). "
    "Never write or edit files directly. "
    "After acting, confirm in one short sentence what changed. "
    "Never repeat, quote, or paste back content you created (briefs, posts, plans, etc.) — user reads it directly in the dashboard. "
    "The current GTM OS state is provided to you at the start of each turn — do "
    "not explore with Read/Grep/Glob to discover existing structure; act directly. "
    "IMPORTANT: update-profile accepts TWO distinct text fields — use --voice for "
    "brand voice & tone, and --brief-spec for post brief spec (output format rules). "
    "Never merge them: if the user provides both, pass each to its own flag. "
    "If updating only one, omit the other flag entirely."
)


def state_snapshot(projects):
    """Render db.tree() output as a compact text outline for the chat agent,
    so it already knows the project/profile/channel structure and need not
    forage. Pure + deterministic — fed a fresh tree each turn."""
    lines = ["## Current GTM OS state"]
    if not projects:
        lines.append("(no projects yet)")
        return "\n".join(lines)
    for p in projects:
        lines.append(f"{p['slug']} ({p.get('kind') or p.get('type')})")
        for prof in p.get("profiles", []):
            lines.append(f"  profile {prof['slug']} \"{prof['name']}\"")
            for ch in prof.get("channels", []):
                lines.append(f"    channel {ch['slug']} ({ch.get('platform')})")
    return "\n".join(lines)


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

    def log_message(self, fmt, *args):
        sys.stderr.write("  [dash] " + (fmt % args) + "\n")

    # -- AI chat (drives a persistent guard-railed ChatSession via SSE) --- #
    def _handle_ask(self, body):
        messages = body.get("messages", [])
        if not messages or messages[-1].get("role") != "user":
            return self._send(400, {"error": "no user message"})
        text = messages[-1]["content"]

        # Client-supplied context (current view + attached file contents from
        # buildContext() in app.html). Placed ahead of the request so the agent
        # sees what the user is looking at and any files they attached.
        text = f"## Request\n{text}"
        context = (body.get("context") or "").strip()
        if context:
            text = f"{context}\n\n{text}"

        try:
            snapshot = state_snapshot(db.tree())
            text = f"{snapshot}\n\n{text}"
        except Exception:  # noqa: BLE001
            pass


        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        try:
            for kind, payload in get_chat_session().ask(text):
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
            return self._send(200, APP_HTML.read_bytes(), "text/html; charset=utf-8")

        if path == "/quit":
            self._send(200, {"ok": True})
            threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
            return

        if path in ("/app.css", "/app.js"):
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
                sid = _CHAT.session_id if _CHAT is not None else None
                return self._send(200, {"session_id": sid})
            if path == "/api/timeline":
                return self._send(200, db.timeline())
            if path == "/api/tree":
                return self._send(200, db.tree())
            if path == "/api/posts-index":
                return self._send(200, db.posts())
            if path.startswith("/api/project/"):
                slug = path[len("/api/project/"):]
                data = db.project(slug)
                if data is None:
                    return self._send(404, {"error": f"project '{slug}' not found"})
                for m in data["memos"]:
                    m["body"] = fileops.read_authored_json(m.get("file_path"))
                for x in data["experiments"]:
                    x["body"] = fileops.read_authored_json(x.get("file_path"))
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
                return self._send(200, fileops.read_detail(post_id))
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
            if path.startswith("/api/profile/") and path.endswith("/plan"):
                slug = path[len("/api/profile/"):-len("/plan")]
                return self._send(200, {"ok": True, **fileops.run_plan(slug, body)})
            if path.startswith("/api/post/") and path.endswith("/update"):
                post_id = path[len("/api/post/"):-len("/update")]
                return self._send(200, {"ok": True, **fileops.update_post(post_id, body)})
            if path == "/api/posts/delete":
                return self._send(200, {"ok": True, **fileops.delete_posts(body.get("ids", []))})
            if path.startswith("/api/post/") and path.endswith("/delete"):
                post_id = path[len("/api/post/"):-len("/delete")]
                return self._send(200, {"ok": True, **fileops.delete_post(post_id)})
            if path.startswith("/api/post/") and path.endswith("/status"):
                post_id = path[len("/api/post/"):-len("/status")]
                result = fileops.set_status(post_id, body.get("status"))
                return self._send(200, {"ok": True, **result})
            if path.startswith("/api/post/") and path.endswith("/brief"):
                post_id = path[len("/api/post/"):-len("/brief")]
                result = fileops.generate_brief(post_id)
                return self._send(200, {"ok": True, **result})
            if path.startswith("/api/post/") and path.endswith("/revise"):
                post_id = path[len("/api/post/"):-len("/revise")]
                result = fileops.revise_post(post_id, body.get("instruction", ""))
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
