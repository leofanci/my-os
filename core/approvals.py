"""approvals.py — proposals waiting on the CEO (Slack-style approvals inbox).

A bot that proposes a write and waits for the user's OK ends its reply with one
line `APPROVAL: <what it will save, where>`. The server strips that line,
records a pending approval for the thread, and the UI shows Approve / Edit / No
on the reply plus an inbox (HQ lists every workspace, a company only its own).
Any new user message in that thread resolves it.

Stored in gitignored team/approvals.json (spans workspaces, so company bots
are denied Read on team/).
"""
import json
import re
import time
import uuid
from pathlib import Path

from core import bots

MARKER_RE = re.compile(r"^[ \t>*_-]*APPROVAL:[*_ \t]*(.+?)[ \t*_]*$", re.M)
SUMMARY_MAX = 200
KEEP = 200
STATUSES = {"pending", "approved", "rejected", "answered", "superseded"}


def extract(reply):
    """(reply without APPROVAL lines, last summary or None)."""
    found = MARKER_RE.findall(reply or "")
    if not found:
        return reply, None
    clean = MARKER_RE.sub("", reply).rstrip()
    return clean, found[-1].strip()[:SUMMARY_MAX] or None


def _path(root):
    return Path(root) / "team" / "approvals.json"


def load(root=bots.ROOT):
    try:
        data = json.loads(_path(root).read_text())
    except (OSError, ValueError):
        return []
    rows = data.get("approvals") if isinstance(data, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and r.get("id")]


def _save(root, rows):
    bots._atomic_write(_path(root), json.dumps({"approvals": rows[-KEEP:]}, indent=2) + "\n")


def add(root=bots.ROOT, *, ws, room, chat, bot, summary):
    """Record a pending approval; an older pending one in the same thread is superseded."""
    rows = load(root)
    for r in rows:
        if r.get("chat") == chat and r.get("status") == "pending":
            r["status"] = "superseded"
    rec = {"id": uuid.uuid4().hex[:12], "ws": ws, "room": room, "chat": chat, "bot": bot,
           "summary": summary, "created": time.time(), "status": "pending"}
    rows.append(rec)
    _save(root, rows)
    return rec


def resolve_chat(chat, status, root=bots.ROOT):
    """Close the thread's pending approval (the user answered it)."""
    if status not in STATUSES or not chat:
        return 0
    rows = load(root)
    n = 0
    for r in rows:
        if r.get("chat") == chat and r.get("status") == "pending":
            r["status"], r["resolved"] = status, time.time()
            n += 1
    if n:
        _save(root, rows)
    return n


def pending(root=bots.ROOT, ws=None):
    """Open approvals, newest first; `ws` other than HQ narrows to one workspace."""
    rows = [r for r in load(root) if r.get("status") == "pending"
            and (not ws or ws == bots.HQ or r.get("ws") == ws)]
    return sorted(rows, key=lambda r: r.get("created") or 0, reverse=True)
