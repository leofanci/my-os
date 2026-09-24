"""chat_store.py — saved AI chats (one JSON file per chat, gitignored).

Each chat is its own Claude Code session: the file id IS the claude session id,
so reopening a chat resumes that exact context via --resume, and a new chat is
a genuinely fresh session. The file holds the visible transcript plus the few
ChatSession fields needed to resume correctly after a dashboard restart.
"""
import json
import os
import re
import tempfile
import time
from pathlib import Path

CHATS_DIR = Path(__file__).resolve().parent.parent / "chats"
_ID_RE = re.compile(r"^[0-9a-f-]{36}$")
TITLE_MAX = 60


def _path(chat_id):
    if not isinstance(chat_id, str) or not _ID_RE.match(chat_id):
        raise ValueError("invalid chat id")
    return CHATS_DIR / f"{chat_id}.json"


def title_from(text):
    t = re.sub(r"(?:^|\s)/[\w.-]+", " ", text or "")  # drop /skill tags, keep @mentions
    t = " ".join(t.split())
    return (t[:TITLE_MAX - 1] + "…") if len(t) > TITLE_MAX else (t or "New chat")


def load(chat_id):
    try:
        return json.loads(_path(chat_id).read_text())
    except (ValueError, FileNotFoundError):  # bad id, missing, or corrupt JSON
        return None


def save(rec):
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    target = _path(rec["id"])
    fd, tmp = tempfile.mkstemp(dir=CHATS_DIR, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, target)


def delete(chat_id):
    try:
        _path(chat_id).unlink()
        return True
    except FileNotFoundError:
        return False


def list_meta():
    """Newest first; transcript omitted."""
    out = []
    for f in CHATS_DIR.glob("*.json") if CHATS_DIR.is_dir() else []:
        try:
            rec = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        out.append({k: rec.get(k) for k in ("id", "title", "created", "updated", "turn_count")})
    return sorted(out, key=lambda r: r.get("updated") or 0, reverse=True)


def record_turn(sess, scope, user_msg, reply):
    """Append one exchange to the chat backing `sess` and snapshot its resume state."""
    rec = load(sess.session_id) or {
        "id": sess.session_id,
        "title": title_from(user_msg),
        "created": time.time(),
        "messages": [],
    }
    rec["messages"].append({"role": "user", "content": user_msg})
    if reply:
        rec["messages"].append({"role": "assistant", "content": reply})
    rec.update({
        "updated": time.time(),
        "scope": list(scope) if scope else None,
        "started": not sess.is_fresh(),
        "turn_count": sess._turn_count,
        "last_skill": sess._last_skill,
        "skill_explicit": sess._skill_explicit,
    })
    save(rec)
    return rec
