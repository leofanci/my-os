"""rooms.py — Slack-style channels and DMs ("rooms" in code: "channel" already
means a social channel of a profile).

Kinds (id prefix):
  hq          #hq: cross-project, every active bot, led by Chief of Staff
  p-<slug>    one per project (implicit, never stored), every active bot
  t-<name>    topic channel: user-created, picked project (or none), members, lead
  dm-<bot>    1:1 with one bot; no project unless the user @mentions one

Only topic channels are stored, in gitignored team/rooms.json. A room costs
nothing by itself: untagged messages go to ONE bot (the lead), members answer
only when tagged, and the persona's team list shrinks to the members.
"""
import json
import re
from pathlib import Path

from core import bots

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def _path(root):
    return Path(root) / "team" / "rooms.json"


def _load_topics(root):
    try:
        data = json.loads(_path(root).read_text())
    except (OSError, ValueError):
        return []
    rows = data.get("topics") if isinstance(data, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and _NAME_RE.match(str(r.get("name", "")))]


def _save_topics(root, rows):
    bots._atomic_write(_path(root), json.dumps({"topics": rows}, indent=2) + "\n")


def list_rooms(team, projects, root=bots.ROOT):
    """All rooms in sidebar order: hq, projects, topics, DMs."""
    active = [b.id for b in team.ordered() if b.active]
    slugs = {p.get("slug") for p in projects}
    out = [{"id": "hq", "kind": "hq", "name": "hq", "project": None,
            "members": active, "lead": bots.ROOT_BOT}]
    for p in projects:
        out.append({"id": f"p-{p['slug']}", "kind": "project", "name": p["slug"],
                    "label": p.get("name") or p["slug"], "project": p["slug"],
                    "members": active, "lead": bots.ROOT_BOT})
    for t in _load_topics(root):
        project = t.get("project") if t.get("project") in slugs else None
        members = [m for m in t.get("members") or [] if team.get(m) and team.get(m).active]
        lead = team.resolve(t.get("lead") or bots.ROOT_BOT)
        if lead not in members:
            members.insert(0, lead)
        out.append({"id": f"t-{t['name']}", "kind": "topic", "name": t["name"],
                    "project": project, "members": members, "lead": lead})
    for b in team.ordered():
        if b.active:
            out.append({"id": f"dm-{b.id}", "kind": "dm", "name": b.name, "project": None,
                        "members": [b.id], "lead": b.id})
    return out


def get_room(room_id, team, projects, root=bots.ROOT):
    return next((r for r in list_rooms(team, projects, root) if r["id"] == room_id), None)


def save_topic(name, project, members, lead, projects, root=bots.ROOT, *, replace=None):
    """Create a topic channel, or update `replace` (its current name)."""
    name = (name or "").strip().lower()
    if not _NAME_RE.match(name):
        raise ValueError("channel name: lowercase letters, digits, dashes (max 40)")
    slugs = {p.get("slug") for p in projects}
    if name == "hq" or name in slugs:
        raise ValueError(f"#{name} is already a channel")
    if project and project not in slugs:
        raise ValueError(f"unknown project: {project}")
    defs = bots.load_defs()
    members = [m for m in dict.fromkeys(members or []) if m in defs]
    if lead not in defs:
        raise ValueError("pick a lead bot")
    if lead not in members:
        members.insert(0, lead)
    rows = _load_topics(root)
    if any(r["name"] == name for r in rows) and name != replace:
        raise ValueError(f"#{name} already exists")
    row = {"name": name, "project": project or None, "members": members, "lead": lead}
    if replace:
        if not any(r["name"] == replace for r in rows):
            raise ValueError(f"unknown channel: #{replace}")
        rows = [row if r["name"] == replace else r for r in rows]
    else:
        rows.append(row)
    _save_topics(root, rows)
    return f"t-{name}"


def delete_topic(name, root=bots.ROOT):
    rows = _load_topics(root)
    keep = [r for r in rows if r["name"] != name]
    if len(keep) == len(rows):
        raise ValueError(f"unknown channel: #{name}")
    _save_topics(root, keep)


def room_of_chat(rec, room_ids):
    """Room a saved chat lists under. Chats from before rooms existed (or whose
    topic channel was deleted) fall back to their project room, then #hq."""
    rid = rec.get("room")
    if rid in room_ids:
        return rid
    scope = rec.get("scope")
    if scope and f"p-{scope[0]}" in room_ids:
        return f"p-{scope[0]}"
    return "hq"
