"""gtm.py — Go-to-market phases + strategies (the sec07 tab).

Files-as-truth, lens model. A **phase** is a time-boxed bet ("first 10 customers");
a **strategy** is a channel-motion ("LinkedIn founder-led outbound") inside a phase.
Experiments (and the launch memo) tagged with `strategy: <composed-id>` keep living in
their home tabs — the GTM tab pulls them in by tag, so nothing is duplicated here.

Storage, per project:
    projects/<slug>/gtm/phases.json
        {"phases": [{"id","name","goal","timebox","status"}]}   (ordered)
    projects/<slug>/gtm/strategy-<stem>.json
        {"stem","phase","name","channel_slug","hypothesis","status","primary","notes"}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PHASE_STATUSES = frozenset({"planned", "active", "done"})
STRATEGY_STATUSES = frozenset({"proposed", "active", "paused", "killed"})

GTM_DIRNAME = "gtm"
PHASES_FILE = "phases.json"
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


# --------------------------------------------------------------------------- #
# paths + slug
# --------------------------------------------------------------------------- #

def gtm_dir(root: Path, project_slug: str) -> Path:
    if not _SAFE_COMPONENT_RE.fullmatch(str(project_slug or "")):
        raise ValueError("invalid project slug")
    return Path(root) / "projects" / project_slug / GTM_DIRNAME


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "untitled"


# --------------------------------------------------------------------------- #
# normalize
# --------------------------------------------------------------------------- #

def normalize_phase(body: dict | None) -> dict:
    src = dict(body or {})
    name = str(src.get("name") or "").strip()
    pid = str(src.get("id") or "").strip() or slugify(name)
    status = str(src.get("status") or "planned").strip().lower()
    if status not in PHASE_STATUSES:
        status = "planned"
    return {
        "id": pid,
        "name": name,
        "goal": str(src.get("goal") or "").strip(),
        "timebox": str(src.get("timebox") or "").strip(),
        "status": status,
    }


def normalize_strategy(body: dict | None) -> dict:
    src = dict(body or {})
    name = str(src.get("name") or "").strip()
    stem = str(src.get("stem") or "").strip() or slugify(name)
    status = str(src.get("status") or "proposed").strip().lower()
    if status not in STRATEGY_STATUSES:
        status = "proposed"
    return {
        "stem": stem,
        "phase": str(src.get("phase") or "").strip(),
        "name": name,
        "channel_slug": str(src.get("channel_slug") or src.get("channel") or "").strip(),
        "hypothesis": str(src.get("hypothesis") or "").strip(),
        "status": status,
        "primary": bool(src.get("primary")),
        "notes": str(src.get("notes") or "").strip(),
    }


def dumps_json(body: Any) -> str:
    return json.dumps(body, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# load / save
# --------------------------------------------------------------------------- #

def load_phases(root: Path, project_slug: str) -> list[dict]:
    """Ordered, normalized phases for a project (empty if none)."""
    path = gtm_dir(root, project_slug) / PHASES_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = data.get("phases") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    return [normalize_phase(p) for p in raw if isinstance(p, dict)]


def save_phases(root: Path, project_slug: str, phases: list[dict]) -> Path:
    d = gtm_dir(root, project_slug)
    d.mkdir(parents=True, exist_ok=True)
    path = d / PHASES_FILE
    norm = [normalize_phase(p) for p in phases]
    path.write_text(dumps_json({"phases": norm}), encoding="utf-8")
    return path


def load_strategies(root: Path, project_slug: str) -> list[dict]:
    """All strategy-*.json for a project, normalized, sorted by stem."""
    d = gtm_dir(root, project_slug)
    if not d.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(d.glob("strategy-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        stem = f.stem[len("strategy-"):]
        data.setdefault("stem", stem)
        out.append(normalize_strategy(data))
    return out


def strategy_path(root: Path, project_slug: str, stem: str) -> Path:
    if not _SAFE_COMPONENT_RE.fullmatch(str(stem or "")):
        raise ValueError("invalid strategy stem")
    return gtm_dir(root, project_slug) / f"strategy-{stem}.json"


def save_strategy(root: Path, project_slug: str, body: dict) -> Path:
    norm = normalize_strategy(body)
    d = gtm_dir(root, project_slug)
    d.mkdir(parents=True, exist_ok=True)
    path = strategy_path(root, project_slug, norm["stem"])
    path.write_text(dumps_json(norm), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# the lens — children tagged to a strategy, read from their home tabs
# --------------------------------------------------------------------------- #

def experiment_tags(root: Path, project_slug: str) -> dict[str, list[str]]:
    """strategy-stem → [experiment stems tagged to it]. The tag lives on the
    experiment JSON (`strategy` field), pointing up — GTM never copies it in."""
    exp_dir = gtm_dir(root, project_slug).parent / "strategy" / "experiments"
    out: dict[str, list[str]] = {}
    if not exp_dir.is_dir():
        return out
    for f in sorted(exp_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        tag = str(data.get("strategy") or "").strip()
        if tag:
            out.setdefault(tag, []).append(f.stem)
    return out


# --------------------------------------------------------------------------- #
# the assembled tab view — phases → strategies → tagged experiments,
# with composed ids resolved. Built where a registry is available (server.py).
# --------------------------------------------------------------------------- #

def _exp_stem(exp: dict) -> str:
    if exp.get("stem"):
        return exp["stem"]
    fp = exp.get("file_path") or ""
    return fp.rsplit("/", 1)[-1].replace(".json", "") if fp else ""


def build_view(root: Path, project_slug: str, registry, experiments: list[dict] | None = None) -> dict:
    """Nested GTM view for the dashboard: phases, each with its strategies, each
    strategy with the experiments tagged to it (the lens). `registry` resolves
    composed ids; `experiments` is the project's enriched experiment list."""
    from core.ids import lk_experiment, lk_phase, lk_strategy

    experiments = experiments or []
    exp_by_stem: dict[str, dict] = {}
    for x in experiments:
        stem = _exp_stem(x)
        if stem:
            exp_by_stem[stem] = x
    tags = experiment_tags(root, project_slug)  # strategy-stem → [exp stems]

    def _rid(key: str) -> str | None:
        return registry.get(key) if registry else key

    def _strategy_node(s: dict) -> dict:
        stem = s["stem"]
        exps = []
        for est in tags.get(stem, []):
            x = exp_by_stem.get(est, {})
            exps.append({
                "id": x.get("id") or _rid(lk_experiment(project_slug, est)),
                "stem": est,
                "assumption": x.get("assumption") or "",
                "status": x.get("status") or "",
            })
        return {
            "id": _rid(lk_strategy(project_slug, stem)),
            "stem": stem,
            "name": s["name"],
            "channel_slug": s["channel_slug"],
            "hypothesis": s["hypothesis"],
            "status": s["status"],
            "primary": s["primary"],
            "notes": s["notes"],
            "experiments": exps,
        }

    strategies = load_strategies(root, project_slug)
    phases = load_phases(root, project_slug)
    phase_ids = {p["id"] for p in phases}

    strat_nodes = [_strategy_node(s) for s in strategies]
    by_phase: dict[str, list[dict]] = {}
    for s, node in zip(strategies, strat_nodes):
        by_phase.setdefault(s["phase"], []).append(node)

    phase_nodes = [{
        "id": _rid(lk_phase(project_slug, p["id"])),
        "phase_id": p["id"],
        "name": p["name"],
        "goal": p["goal"],
        "timebox": p["timebox"],
        "status": p["status"],
        "strategies": by_phase.get(p["id"], []),
    } for p in phases]

    unphased = [n for s, n in zip(strategies, strat_nodes)
                if s["phase"] not in phase_ids]
    primary = next((n["stem"] for n in strat_nodes if n["primary"]), None)

    return {"phases": phase_nodes, "unphased": unphased, "primary": primary}
