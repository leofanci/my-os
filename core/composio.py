"""composio.py — stdlib client for the user's own Composio project (connected apps).

Only the dashboard server calls this; the key never leaves its process. Every
request goes through one opener that refuses redirects (urllib would copy the
x-api-key header to the redirect target). `execute` is never retried: a retry
after a timeout can send an email twice.

Response shapes follow Composio's v3.1 docs (Oct 2026); each endpoint parses in
one `_parse_*` helper so a live check can correct it in one place.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from core import app_rules, bots, integrations

BASE = "https://backend.composio.dev/api/v3.1"
TIMEOUT = 30
CATALOG_TTL = 3600
CATALOG_MAX_PAGES = 20
_CATALOG = {}  # {"at": ts, "items": [...]}: one install, one Composio project


class ComposioError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 3xx surfaces as HTTPError → ComposioError


_opener = urllib.request.build_opener(_NoRedirect)


def trusted_mcp_url(url):
    try:
        u = urllib.parse.urlsplit(url or "")
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host == "composio.dev" or host.endswith(".composio.dev"))


def _key(root):
    key = integrations.api_key(root)
    if not key:
        raise ComposioError("Composio is not configured")
    return key


def _send(method, url, body, root, headers=None):
    """(status, headers, raw body). Errors never carry request headers."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-api-key", _key(root))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        raise ComposioError(f"Composio HTTP {e.code}", status=e.code) from None
    except (urllib.error.URLError, OSError) as e:  # TimeoutError is an OSError
        raise ComposioError(f"Composio unreachable ({type(e).__name__})") from None


def _json(method, path, body, root):
    _, _, raw = _send(method, BASE + path, body, root)
    try:
        return json.loads(raw.decode() or "{}")
    except ValueError:
        raise ComposioError("Composio returned invalid JSON") from None


def _parse_session(data):
    sid = data.get("session_id")
    url = (data.get("mcp") or {}).get("url")
    if not sid or not trusted_mcp_url(url):
        raise ComposioError("Composio returned an untrusted session")
    return {"session_id": sid, "mcp_url": url}


def ensure_session(pid, root=bots.ROOT):
    """The person's locked-down session, created once and reused."""
    _key(root)
    row = integrations.person(pid, root)
    if row.get("session_id") and trusted_mcp_url(row.get("mcp_url")):
        return {"session_id": row["session_id"], "mcp_url": row["mcp_url"]}
    body = {"user_id": row["composio_user_id"],
            "toolkits": {"disable": sorted(app_rules.BLOCKED_TOOLKITS)},
            "manage_connections": {"enable": False},
            "workbench": {"enable": False}}
    sess = _parse_session(_json("POST", "/tool_router/session", body, root))
    integrations.save_session(pid, sess["session_id"], sess["mcp_url"], root)
    return sess


def reset_session(pid, root=bots.ROOT):
    """Forget a gone session (401/404); connections live on the Composio user."""
    integrations.forget_session(pid, root)


def _auth_kind(item):
    if item.get("composio_managed_auth_schemes"):
        return "managed"
    if "API_KEY" in [str(s).upper() for s in item.get("auth_schemes") or []]:
        return "api_key"
    return "own_app"


def _parse_catalog_page(data):
    items = [{"slug": i["slug"], "name": i.get("name") or i["slug"],
              "logo": (i.get("meta") or {}).get("logo"), "auth": _auth_kind(i)}
             for i in data.get("items") or [] if isinstance(i, dict) and i.get("slug")]
    return items, data.get("next_cursor")


def catalog(root=bots.ROOT):
    """Every toolkit, most used first, blocklist removed; cached an hour."""
    if _CATALOG and time.time() - _CATALOG["at"] < CATALOG_TTL:
        return _CATALOG["items"]
    items, cursor = [], None
    for _ in range(CATALOG_MAX_PAGES):
        q = {"limit": "500", "sort_by": "usage", **({"cursor": cursor} if cursor else {})}
        page, cursor = _parse_catalog_page(_json("GET", "/toolkits?" + urllib.parse.urlencode(q), None, root))
        items += page
        if not cursor:
            break
    items = [i for i in items if i["slug"] not in app_rules.BLOCKED_TOOLKITS]
    _CATALOG.update(at=time.time(), items=items)
    return items


def connect_link(pid, toolkit, root=bots.ROOT):
    sid = ensure_session(pid, root)["session_id"]
    data = _json("POST", f"/tool_router/session/{urllib.parse.quote(sid)}/link", {"toolkit": toolkit}, root)
    url = data.get("redirect_url") or data.get("url")
    if not url:
        raise ComposioError("Composio returned no connect link")
    return url


def _parse_connections(data):
    return {i["slug"] for i in data.get("items") or []
            if isinstance(i, dict) and i.get("slug")
            and ((i.get("connected_account") or {}).get("status") == "ACTIVE")}


def connections(pid, root=bots.ROOT):
    sid = ensure_session(pid, root)["session_id"]
    return _parse_connections(_json("GET", f"/tool_router/session/{urllib.parse.quote(sid)}/toolkits", None, root))


def execute(pid, slug, arguments, root=bots.ROOT):
    """Run one approved tool call, exactly once."""
    sid = ensure_session(pid, root)["session_id"]
    return _json("POST", f"/tool_router/session/{urllib.parse.quote(sid)}/execute",
                 {"tool_slug": slug, "arguments": arguments or {}}, root)


def _parse_rpc(raw, ctype):
    text = raw.decode(errors="replace").strip()
    if not text:
        return None
    if "text/event-stream" in (ctype or ""):
        datas = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        text = datas[-1] if datas else ""
        if not text:
            return None
    try:
        return json.loads(text)
    except ValueError:
        raise ComposioError("Composio MCP returned invalid JSON") from None


def forward(mcp_url, frame, mcp_session_id, root=bots.ROOT):
    """POST one JSON-RPC frame to the session MCP URL; (reply or None, session header)."""
    if not trusted_mcp_url(mcp_url):
        raise ComposioError("untrusted MCP URL")
    headers = {"Accept": "application/json, text/event-stream"}
    if mcp_session_id:
        headers["mcp-session-id"] = mcp_session_id
    _, resp_headers, raw = _send("POST", mcp_url, frame, root, headers)
    return (_parse_rpc(raw, resp_headers.get("Content-Type")),
            resp_headers.get("mcp-session-id") or mcp_session_id)
