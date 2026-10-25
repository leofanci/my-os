"""rooms.py — Slack-style channels and DMs inside a workspace ("rooms" in code:
"channel" already means a social channel of a profile).

A workspace is HQ (the holding's CEO office) or one project (one company).
Every room id is `<workspace>/<local>`:
  <ws>/general     the workspace's main channel, led by Chief of Staff
  <ws>/t-<name>    topic channel: user-created, members + lead
  <ws>/dm-<bot>    1:1 with one of the workspace's active bots

A project workspace's rooms are bound to that project; nothing in one
workspace is visible from another. Topic channels are stored per workspace
(team/rooms.json for HQ, projects/<slug>/team/rooms.json otherwise).

A room costs nothing by itself: untagged messages go to ONE bot (the lead),
members answer only when tagged, and the persona's team list shrinks to them.
"""
import json
import re

from core import bots

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_RESERVED = {"general"}


def split_id(room_id):
    """'acme/t-launch' → ('acme', 't-launch'); malformed → (None, None)."""
    ws, sep, local = str(room_id or "").partition("/")
    return (ws, local) if sep and ws and local else (None, None)


def _load_topics(ws, root):
    try:
        data = json.loads((bots.ws_dir(ws, root) / "rooms.json").read_text())
    except (OSError, ValueError):
        return []
    rows = data.get("topics") if isinstance(data, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and _NAME_RE.match(str(r.get("name", "")))]


def _save_topics(ws, root, rows):
    bots._atomic_write(bots.ws_dir(ws, root) / "rooms.json", json.dumps({"topics": rows}, indent=2) + "\n")


def list_rooms(team, ws, root=bots.ROOT):
    """A workspace's rooms in sidebar order: general, topics, DMs."""
    active = [b.id for b in team.ordered() if b.active]
    out = [{"id": f"{ws}/general", "kind": "general", "name": "general",
            "members": active, "lead": bots.ROOT_BOT}]
    for t in _load_topics(ws, root):
        members = [m for m in t.get("members") or [] if team.get(m) and team.get(m).active]
        lead = team.resolve(t.get("lead") or bots.ROOT_BOT)
        if lead not in members:
            members.insert(0, lead)
        out.append({"id": f"{ws}/t-{t['name']}", "kind": "topic", "name": t["name"],
                    "members": members, "lead": lead})
    for b in team.ordered():
        if b.active:
            out.append({"id": f"{ws}/dm-{b.id}", "kind": "dm", "name": b.name,
                        "members": [b.id], "lead": b.id})
    return out


def get_room(room_id, team, root=bots.ROOT):
    ws, _ = split_id(room_id)
    if ws != team.ws:
        return None
    return next((r for r in list_rooms(team, ws, root) if r["id"] == room_id), None)


def save_topic(ws, name, members, lead, root=bots.ROOT, *, replace=None):
    """Create a topic channel in workspace `ws`, or update `replace` (its current name)."""
    name = (name or "").strip().lower()
    if not _NAME_RE.match(name):
        raise ValueError("channel name: lowercase letters, digits, dashes (max 40)")
    if name in _RESERVED:
        raise ValueError(f"#{name} is already a channel")
    defs = bots.load_defs()
    members = [m for m in dict.fromkeys(members or []) if m in defs]
    if lead not in defs:
        raise ValueError("pick a lead bot")
    if lead not in members:
        members.insert(0, lead)
    rows = _load_topics(ws, root)
    if any(r["name"] == name for r in rows) and name != replace:
        raise ValueError(f"#{name} already exists")
    row = {"name": name, "members": members, "lead": lead}
    if replace:
        if not any(r["name"] == replace for r in rows):
            raise ValueError(f"unknown channel: #{replace}")
        rows = [row if r["name"] == replace else r for r in rows]
    else:
        rows.append(row)
    _save_topics(ws, root, rows)
    return f"{ws}/t-{name}"


def delete_topic(ws, name, root=bots.ROOT):
    rows = _load_topics(ws, root)
    keep = [r for r in rows if r["name"] != name]
    if len(keep) == len(rows):
        raise ValueError(f"unknown channel: #{name}")
    _save_topics(ws, root, keep)


def room_of_chat(rec, room_ids, workspaces):
    """Room id a saved chat lists under (`room_ids`: rooms that exist).
    Threads whose topic channel was deleted, or from before workspaces
    existed, land in their project's #general, else HQ's #general."""
    rid = rec.get("room") or ""
    if rid in room_ids:
        return rid
    ws, _ = split_id(rid)
    if ws in workspaces:
        return f"{ws}/general"
    if rid.startswith("p-") and rid[2:] in workspaces:  # pre-workspace project room
        return f"{rid[2:]}/general"
    scope = rec.get("scope")
    if scope and scope[0] in workspaces:
        return f"{scope[0]}/general"
    return f"{bots.HQ}/general"
