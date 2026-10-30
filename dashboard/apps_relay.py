"""apps_relay.py — the only connected-apps endpoint a bot can reach.

An app turn's `claude -p` gets one HTTP MCP server pointing back at the
dashboard (POST /api/internal/apps/mcp) with a per-request turn token. The
relay forwards to the person's Composio session, adding the key, and gates
every call:

  tools/list   only the search, schema and multi-execute meta tools
  tools/call   each app tool inside a multi-execute: read -> runs now,
               not a read on a write grant -> held in Approvals, else refused

The bot's body is never forwarded as is: reads are rebuilt into a fresh
multi-execute, so extra fields (workbench sync, ...) never reach Composio.
The gate talks to an `Upstream` (one `forward` method), so other MCP servers
can sit behind it later without touching it.
"""
import hmac
import secrets
import threading
import time

from core import app_rules, approvals, bots, composio, integrations

MAX_AGE = 1800  # hard cap; a token normally dies with its chat request
METHODS = ("initialize", "ping", "tools/list", "tools/call")
PASS_THROUGH = ("COMPOSIO_SEARCH_TOOLS", "COMPOSIO_GET_TOOL_SCHEMAS")
HELD = "Held for approval ({id}): {title}. It has not run. Tell the user it is waiting in Approvals."
REFUSED = '"{slug}" is not available to this bot. This call was not performed.'
UNREADABLE = "This call could not be read as a list of app tools. It was not performed."


class Tokens:
    """Turn tokens: one per chat request, bound to {ws, bot, chat, room, person}."""

    def __init__(self):
        self._live = {}
        self._lock = threading.Lock()

    def mint(self, ctx):
        token = secrets.token_hex(32)
        with self._lock:
            self._live[token] = (dict(ctx), time.time())
        return token

    def lookup(self, token):
        if not isinstance(token, str) or not token:
            return None
        now = time.time()
        with self._lock:
            for live, (ctx, made) in list(self._live.items()):
                if now - made > MAX_AGE:
                    del self._live[live]
                elif hmac.compare_digest(live, token):
                    return dict(ctx)
        return None

    def revoke(self, token):
        with self._lock:
            self._live.pop(token, None)


TOKENS = Tokens()


class Upstream:
    def forward(self, frame, mcp_session_id):
        """(JSON-RPC reply or None for a notification, mcp-session-id)."""
        raise NotImplementedError


class ComposioUpstream(Upstream):
    def __init__(self, person, root=bots.ROOT):
        self.person, self.root = person, root

    def forward(self, frame, mcp_session_id):
        sess = composio.ensure_session(self.person, self.root)
        try:
            return composio.forward(sess["mcp_url"], frame, mcp_session_id, self.root)
        except composio.ComposioError as e:
            if e.status not in (401, 404):
                raise
        # The session is gone (nothing ran): make a new one and send once more.
        composio.reset_session(self.person, self.root)
        sess = composio.ensure_session(self.person, self.root)
        return composio.forward(sess["mcp_url"], frame, None, self.root)


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _text(rid, lines, is_error=False):
    return {"jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": t} for t in lines], "isError": is_error}}


def _gate(frame, ctx, sid, upstream, root, catalog):
    rid = frame.get("id")
    params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
    name = params.get("name")
    if name in PASS_THROUGH:
        return upstream.forward(frame, sid)
    if name != app_rules.MULTI_EXECUTE:
        return _text(rid, [REFUSED.format(slug=name)], True), sid
    calls = app_rules.calls_in(name, params.get("arguments"))
    if calls is None:
        return _text(rid, [UNREADABLE], True), sid
    grant = integrations.grant(ctx["ws"], ctx["bot"], root)  # re-read: grants change mid-turn
    cat = list(catalog if catalog is not None else [a["slug"] for a in composio.catalog(root)])
    reads, notes = [], []
    for c in calls:
        verdict, tk = app_rules.decide(c["tool_slug"], grant, cat)
        if verdict == "read":
            reads.append(c)
        elif verdict == "hold":
            rec = approvals.add_app_action(root, ws=ctx["ws"], room=ctx.get("room"), chat=ctx.get("chat"),
                                           bot=ctx["bot"], person=ctx["person"], toolkit=tk,
                                           slug=c["tool_slug"], arguments=c["arguments"])
            notes.append(HELD.format(id=rec["id"], title=rec["preview"]["title"]))
        else:
            notes.append(REFUSED.format(slug=c["tool_slug"]))
    if not reads:
        return _text(rid, notes, not any(n.startswith("Held") for n in notes)), sid
    rebuilt = {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
               "params": {"name": app_rules.MULTI_EXECUTE, "arguments": {"tools": reads}}}
    reply, sid = upstream.forward(rebuilt, sid)
    if notes and isinstance(reply, dict) and isinstance(reply.get("result"), dict):
        reply["result"].setdefault("content", []).extend({"type": "text", "text": n} for n in notes)
    return reply, sid


def handle(frame, ctx, mcp_session_id, upstream, root=bots.ROOT, catalog=None):
    """One JSON-RPC frame from a bot -> (reply or None, mcp-session-id)."""
    if not isinstance(frame, dict):
        return _error(None, -32600, "invalid request"), mcp_session_id
    method = frame.get("method") or ""
    if method.startswith("notifications/"):
        return upstream.forward(frame, mcp_session_id)
    if method not in METHODS:
        return _error(frame.get("id"), -32601, "method not available"), mcp_session_id
    if method == "tools/call":
        return _gate(frame, ctx, mcp_session_id, upstream, root, catalog)
    reply, sid = upstream.forward(frame, mcp_session_id)
    if method == "tools/list" and isinstance(reply, dict) and isinstance(reply.get("result"), dict):
        tools = reply["result"].get("tools") or []
        reply["result"]["tools"] = [t for t in tools if isinstance(t, dict) and t.get("name") in app_rules.META_EXPOSED]
    return reply, sid
