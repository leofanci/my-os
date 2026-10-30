"""integrations.py — connected apps state (Composio), in gitignored team/integrations.json.

  composio.api_key   the user's own Composio project key; write-only (public() never returns it)
  people.<pid>       Composio user id (random, never personal) + that person's session
  grants.<ws>.<bot>  toolkit slug -> "read" | "write" ("write" still waits on approval)

A missing HQ Chief of Staff grant falls back to Gmail + Google Calendar; an
explicit {} means the user switched them off. Bots are denied Read on this file
(chat_session.SECRET_FILE_GLOBS).
"""
import json
import re
import secrets
import threading
import time
from pathlib import Path

from core import app_rules, bots

LOCK = threading.Lock()
SCOPES = ("read", "write")
DEFAULT_GRANTS = {bots.HQ: {bots.ROOT_BOT: {"gmail": "write", "googlecalendar": "write"}}}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _path(root):
    return Path(root) / "team" / "integrations.json"


def load(root=bots.ROOT):
    try:
        data = json.loads(_path(root).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(root, data):
    # mkstemp creates the temp file 0600 and os.replace keeps that mode.
    bots._atomic_write(_path(root), json.dumps(data, indent=2) + "\n")


def _update(root, fn):
    with LOCK:
        data = load(root)
        out = fn(data)
        _save(root, data)
        return out


def public(root=bots.ROOT):
    c = load(root).get("composio") or {}
    return {"configured": bool(c.get("api_key")), "saved": c.get("saved")}


def api_key(root=bots.ROOT):
    return (load(root).get("composio") or {}).get("api_key") or None


def set_key(key, root=bots.ROOT):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("api_key required")
    _update(root, lambda d: d.__setitem__("composio", {"api_key": key.strip(), "saved": time.time()}))


def remove_key(root=bots.ROOT):
    """Forget the key and every session made with it; grants stay."""
    def fn(d):
        d.pop("composio", None)
        for row in (d.get("people") or {}).values():
            row.pop("session_id", None)
            row.pop("mcp_url", None)
    _update(root, fn)


def person(pid, root=bots.ROOT):
    def fn(d):
        row = d.setdefault("people", {}).setdefault(pid, {})
        row.setdefault("composio_user_id", "myos-" + secrets.token_hex(8))
        return dict(row)
    return _update(root, fn)


def save_session(pid, session_id, mcp_url, root=bots.ROOT):
    person(pid, root)
    _update(root, lambda d: d["people"][pid].update(session_id=session_id, mcp_url=mcp_url))


def forget_session(pid, root=bots.ROOT):
    def fn(d):
        row = (d.get("people") or {}).get(pid) or {}
        row.pop("session_id", None)
        row.pop("mcp_url", None)
    _update(root, fn)


def grant(ws, bot, root=bots.ROOT):
    stored = ((load(root).get("grants") or {}).get(ws) or {}).get(bot)
    if stored is None:
        stored = (DEFAULT_GRANTS.get(ws) or {}).get(bot) or {}
    return dict(stored)


def all_grants(root=bots.ROOT):
    return load(root).get("grants") or {}


def set_grant(ws, bot, apps, root=bots.ROOT):
    if not isinstance(apps, dict):
        raise ValueError("apps must be an object")
    clean = {}
    for slug, scope in apps.items():
        if not isinstance(slug, str) or not _SLUG_RE.match(slug):
            raise ValueError(f"bad app: {slug!r}")
        if slug in app_rules.BLOCKED_TOOLKITS:
            raise ValueError(f"{slug} cannot be granted")
        if scope not in SCOPES:
            raise ValueError(f"bad scope for {slug}: {scope!r}")
        clean[slug] = scope
    _update(root, lambda d: d.setdefault("grants", {}).setdefault(ws, {}).__setitem__(bot, clean))
    return dict(clean)
