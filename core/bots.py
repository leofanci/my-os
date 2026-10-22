"""bots.py — the team: named bots (Slack-style teammates) that own skills.

Definitions are generic roles, tracked in `bots/<id>.md` (frontmatter + job
description). Which bots are on, and what each one remembers, is user data and
stays gitignored:

  team/state.json                   on/off per bot
  team/memory/<bot>.md              HQ memory (chat not tied to a project)
  projects/<slug>/team/<bot>.md     per-project memory (bots never mix projects)

Every skill always has exactly one owner: a switched-off bot's skills roll up
to its nearest active manager. `cos` is the root and is always on.
"""
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_BOT = "cos"
CEO = "ceo"  # the user; top of the org chart, not a bot
MEMORY_MAX_LINES = 40
MEMORY_TAIL_LINES = 20
MEMORY_LINE_MAX = 300

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_MENTION_RE = re.compile(r"(?<![\w@/])@([a-z][a-z0-9-]*)\b")


@dataclass
class Bot:
    id: str
    name: str
    handle: str
    icon: str
    reports_to: str
    skills: tuple
    default_skill: str
    body: str = ""
    active: bool = True
    covering: list = field(default_factory=list)


def _parse(text):
    fm, body = {}, ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                k, sep, v = line.partition(":")
                if sep:
                    fm[k.strip()] = v.strip()
            body = parts[2].strip()
    return fm, body


def load_defs(root=ROOT):
    """{id: Bot} from bots/*.md. Definitions ship with the code, so callers
    pass a data root only for state/memory; defs default to this checkout."""
    out = {}
    for f in sorted((Path(root) / "bots").glob("*.md")):
        fm, body = _parse(f.read_text(encoding="utf-8"))
        skills = tuple(s.strip() for s in fm.get("skills", "").split(",") if s.strip())
        out[f.stem] = Bot(
            id=f.stem,
            name=fm.get("name", f.stem),
            handle=fm.get("handle", f.stem),
            icon=fm.get("icon", "●"),
            reports_to=fm.get("reports_to", CEO),
            skills=skills,
            default_skill=fm.get("default_skill") or (skills[0] if skills else ""),
            body=body,
        )
    return out


def _state_path(root):
    return Path(root) / "team" / "state.json"


def load_state(root=ROOT):
    try:
        data = json.loads(_state_path(root).read_text())
    except (OSError, ValueError):
        return {}
    return {k: bool(v) for k, v in (data.get("active") or {}).items()} if isinstance(data, dict) else {}


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def set_active(bot_id, active, root=ROOT):
    defs = load_defs()
    if bot_id not in defs:
        raise ValueError(f"unknown bot: {bot_id}")
    if bot_id == ROOT_BOT and not active:
        raise ValueError("Chief of Staff is always on (other bots roll up to it)")
    state = load_state(root)
    state[bot_id] = bool(active)
    _atomic_write(_state_path(root), json.dumps({"active": state}, indent=2) + "\n")
    return team(root)


class Team:
    def __init__(self, defs, state):
        self.bots = defs
        for b in defs.values():
            b.active = b.id == ROOT_BOT or state.get(b.id, True)
        self._owner = {}
        for b in defs.values():
            for s in b.skills:
                self._owner[s] = self._roll_up(b.id)
        for b in defs.values():
            b.covering = [o.id for o in defs.values()
                          if not o.active and o.skills
                          and self._roll_up(o.id) == b.id]

    def manager(self, bot_id):
        b = self.bots.get(bot_id)
        if not b or bot_id == ROOT_BOT:
            return None
        up = b.reports_to
        return up if up in self.bots else ROOT_BOT

    def _roll_up(self, bot_id):
        seen = set()
        while bot_id and bot_id not in seen:
            seen.add(bot_id)
            b = self.bots.get(bot_id)
            if b and b.active:
                return bot_id
            bot_id = self.manager(bot_id)
        return ROOT_BOT

    def get(self, bot_id):
        return self.bots.get(bot_id)

    def resolve(self, bot_id):
        """Active bot standing in for `bot_id` (itself, or its nearest active manager)."""
        return self._roll_up(bot_id)

    def owner(self, skill):
        """Active bot that answers for this skill (unknown skills → cos)."""
        return self._owner.get(skill, ROOT_BOT)

    def skills_of(self, bot_id):
        """Effective skills: own first, then those covered for switched-off reports."""
        b = self.bots.get(bot_id)
        if not b or not b.active:
            return []
        own = [s for s in b.skills]
        extra = [s for s, o in self._owner.items() if o == bot_id and s not in own]
        return own + extra

    def mentioned(self, text):
        """First active bot @handle in the message, else None."""
        handles = {b.handle: b.id for b in self.bots.values() if b.active}
        for h in _MENTION_RE.findall((text or "").lower()):
            if h in handles:
                return handles[h]
        return None

    def roster_line(self, bot_id):
        b = self.bots[bot_id]
        return f"@{b.handle} {b.name}: {', '.join(self.skills_of(bot_id))}"

    def to_api(self):
        return [{
            "id": b.id, "name": b.name, "handle": b.handle, "icon": b.icon,
            "reports_to": b.reports_to, "manager": self.manager(b.id),
            "active": b.active, "locked": b.id == ROOT_BOT,
            "skills": list(b.skills), "effective_skills": self.skills_of(b.id),
            "covering": b.covering, "default_skill": b.default_skill,
            "about": b.body.split("\n", 1)[0],
        } for b in self.ordered()]

    def ordered(self):
        """Org-chart order: depth first from the CEO, siblings by name."""
        out, seen = [], set()

        def walk(parent):
            kids = sorted((b for b in self.bots.values()
                           if b.id not in seen
                           and (b.reports_to == parent
                                or (parent == CEO and b.reports_to not in self.bots))),
                          key=lambda b: (b.id != ROOT_BOT, b.name))
            for b in kids:
                seen.add(b.id)
                out.append(b)
                walk(b.id)

        walk(CEO)
        out += [b for b in self.bots.values() if b.id not in seen]
        return out


def team(root=ROOT):
    """Team with on/off state (and memory) read from data `root`."""
    return Team(load_defs(), load_state(root))


# --------------------------------------------------------------------------- #
# Memory — one short markdown list per bot per project. Never mixes projects.
# --------------------------------------------------------------------------- #
def memory_path(bot_id, project=None, root=ROOT):
    if not _SLUG_RE.match(bot_id or ""):
        raise ValueError("invalid bot id")
    root = Path(root)
    if project:
        if not _SLUG_RE.match(project) or not (root / "projects" / project).is_dir():
            raise ValueError(f"unknown project: {project}")
        return root / "projects" / project / "team" / f"{bot_id}.md"
    return root / "team" / "memory" / f"{bot_id}.md"


def read_memory(bot_id, project=None, root=ROOT, tail=MEMORY_TAIL_LINES):
    try:
        lines = memory_path(bot_id, project, root).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return ""
    lines = [ln for ln in lines if ln.strip()]
    return "\n".join(lines[-tail:]) if tail else "\n".join(lines)


def remember(bot_id, text, project=None, root=ROOT, today=None):
    """Append one dated line to the bot's memory for this project (or HQ)."""
    if bot_id not in load_defs():
        raise ValueError(f"unknown bot: {bot_id}")
    line = " ".join((text or "").split())
    if not line:
        raise ValueError("empty memory")
    if len(line) > MEMORY_LINE_MAX:
        raise ValueError(f"memory line over {MEMORY_LINE_MAX} chars; keep it to one fact")
    path = memory_path(bot_id, project, root)
    existing = read_memory(bot_id, project, root, tail=0)
    lines = existing.splitlines() if existing else []
    lines.append(f"- {(today or date.today()).isoformat()} {line}")
    _atomic_write(path, "\n".join(lines[-MEMORY_MAX_LINES:]) + "\n")
    return str(path.relative_to(Path(root)))
