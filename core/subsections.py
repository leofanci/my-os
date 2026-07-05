"""Per-project tab subsections — canonical config + sync with markdown docs.

Nomenclature:
  - **tab** — fixed left-panel project section (overview, validation, …)
  - **subsection** — ordered ``##`` heading inside a tab's markdown doc

Config lives at ``projects/<slug>/subsections.json``. All writes (osctl, dashboard,
index normalize) read/update this file and normalize docs against it. Extra ``##``
headings found in a doc are appended to the project's subsection list (manual edits
stick).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.project_schemas import (
    INTAKE_SECTIONS,
    INTAKE_TITLE,
    INTAKE_VALIDATION_TAB_SECTIONS,
    ROADMAP_SECTIONS,
    ROADMAP_TITLE,
    TECHNICAL_SECTIONS,
    TECHNICAL_TITLE,
    build_markdown_starter,
    normalize_markdown,
    parse_markdown_sections,
)

CONFIG_VERSION = 1
CONFIG_FILENAME = "subsections.json"

DOC_KEYS = ("intake", "technical", "roadmap")

DOC_META: dict[str, dict[str, str]] = {
    "intake": {"path": "strategy/intake.md", "title": INTAKE_TITLE, "tab": "validation"},
    "technical": {"path": "technical.md", "title": TECHNICAL_TITLE, "tab": "technical"},
    "roadmap": {"path": "products/<product>/roadmap.md", "title": ROADMAP_TITLE, "tab": "product"},
}

DEFAULT_SUBSECTIONS: dict[str, tuple[str, ...]] = {
    "intake": INTAKE_SECTIONS,
    "technical": TECHNICAL_SECTIONS,
    "roadmap": ROADMAP_SECTIONS,
}

DEFAULT_VALIDATION_TAB: tuple[str, ...] = INTAKE_VALIDATION_TAB_SECTIONS


def default_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "docs": {k: list(v) for k, v in DEFAULT_SUBSECTIONS.items()},
        "validation_tab": list(DEFAULT_VALIDATION_TAB),
    }


def config_path(root: Path, project_slug: str) -> Path:
    return Path(root) / "projects" / project_slug / CONFIG_FILENAME


def _normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_config()
    if not raw:
        return base
    docs_in = raw.get("docs") if isinstance(raw.get("docs"), dict) else {}
    for key in DOC_KEYS:
        vals = docs_in.get(key)
        if isinstance(vals, list) and vals:
            cleaned = [_clean_title(v) for v in vals if _clean_title(v)]
            if cleaned:
                base["docs"][key] = cleaned
    vt = raw.get("validation_tab")
    if isinstance(vt, list) and vt:
        base["validation_tab"] = [_clean_title(v) for v in vt if _clean_title(v)]
    return base


def _clean_title(value: Any) -> str:
    return str(value or "").strip()


def load_config(root: Path, project_slug: str) -> dict[str, Any]:
    """Return project subsection config (defaults if file missing)."""
    path = config_path(root, project_slug)
    if not path.is_file():
        return default_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    return _normalize_config(raw if isinstance(raw, dict) else None)


def save_config(root: Path, project_slug: str, config: dict[str, Any]) -> dict[str, Any]:
    cfg = _normalize_config(config)
    proj = Path(root) / "projects" / project_slug
    if not proj.is_dir():
        raise ValueError(f"project '{project_slug}' not found")
    path = config_path(root, project_slug)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cfg


def ensure_config(root: Path, project_slug: str) -> dict[str, Any]:
    """Load config or write defaults to disk."""
    path = config_path(root, project_slug)
    if path.is_file():
        return load_config(root, project_slug)
    return save_config(root, project_slug, default_config())


def subsections_for_doc(config: dict[str, Any], doc_key: str) -> tuple[str, ...]:
    if doc_key not in DOC_KEYS:
        raise ValueError(f"unknown doc '{doc_key}' — use one of: {', '.join(DOC_KEYS)}")
    vals = (config.get("docs") or {}).get(doc_key) or []
    return tuple(vals) if vals else DEFAULT_SUBSECTIONS[doc_key]


def validation_tab_subsections(config: dict[str, Any]) -> tuple[str, ...]:
    vals = config.get("validation_tab") or []
    if vals:
        return tuple(vals)
    intake = subsections_for_doc(config, "intake")
    return tuple(s for s in intake if s != "What it is")


def _headings_in_text(text: str, *, roadmap: bool = False) -> list[str]:
    parsed = parse_markdown_sections(text or "", roadmap=roadmap)
    return [k for k in parsed if k != "_preamble"]


def merge_headings_into_config(
    config: dict[str, Any],
    doc_key: str,
    text: str,
    *,
    roadmap: bool = False,
) -> dict[str, Any]:
    """Append ``##`` headings from *text* not already in the doc subsection list."""
    cfg = _normalize_config(config)
    old_titles = {s.lower() for s in subsections_for_doc(cfg, doc_key)}
    existing = list(subsections_for_doc(cfg, doc_key))
    seen = {s.lower() for s in existing}
    for title in _headings_in_text(text, roadmap=roadmap):
        if title.lower() not in seen:
            existing.append(title)
            seen.add(title.lower())
    cfg["docs"][doc_key] = existing
    if doc_key == "intake":
        # Only newly discovered intake headings join validation_tab — never expand
        # an explicit subset on reindex/normalize.
        vt = list(validation_tab_subsections(cfg))
        vt_seen = {s.lower() for s in vt}
        for title in existing:
            if title == "What it is" or title.lower() in old_titles:
                continue
            if title.lower() not in vt_seen:
                vt.append(title)
                vt_seen.add(title.lower())
        cfg["validation_tab"] = vt
    return cfg


def normalize_doc_text(
    text: str,
    *,
    doc_key: str,
    config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Merge headings, normalize markdown, return (text, updated config)."""
    roadmap = doc_key == "roadmap"
    cfg = merge_headings_into_config(config, doc_key, text, roadmap=roadmap)
    sections = subsections_for_doc(cfg, doc_key)
    meta = DOC_META[doc_key]
    normalized = normalize_markdown(
        text or "",
        title=meta["title"],
        sections=sections,
        roadmap=roadmap,
    )
    return normalized, cfg


def starter_text(config: dict[str, Any], doc_key: str) -> str:
    meta = DOC_META[doc_key]
    return build_markdown_starter(meta["title"], subsections_for_doc(config, doc_key))


def subsections_api_payload(config: dict[str, Any]) -> dict[str, Any]:
    cfg = _normalize_config(config)
    return {
        "docs": {k: list(subsections_for_doc(cfg, k)) for k in DOC_KEYS},
        "validation_tab": list(validation_tab_subsections(cfg)),
    }


def schemas_subsections_meta() -> dict[str, Any]:
    return {
        "config_path": f"projects/<slug>/{CONFIG_FILENAME}",
        "docs": {
            key: {
                "default_subsections": list(DEFAULT_SUBSECTIONS[key]),
                "path": DOC_META[key]["path"],
                "tab": DOC_META[key]["tab"],
            }
            for key in DOC_KEYS
        },
        "validation_tab_default": list(DEFAULT_VALIDATION_TAB),
        "feature_section_source": "project.subsections.docs.roadmap",
    }


def parse_subsections_arg(raw: str) -> list[str]:
    """Parse comma- or newline-separated subsection titles."""
    parts = re.split(r"[\n,]+", raw or "")
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = _clean_title(p)
        if t and t.lower() not in seen:
            out.append(t)
            seen.add(t.lower())
    return out


def set_doc_subsections(config: dict[str, Any], doc_key: str, titles: list[str]) -> dict[str, Any]:
    if doc_key not in DOC_KEYS:
        raise ValueError(f"unknown doc '{doc_key}'")
    if not titles:
        raise ValueError("at least one subsection title required")
    cfg = _normalize_config(config)
    cfg["docs"][doc_key] = [_clean_title(t) for t in titles if _clean_title(t)]
    if doc_key == "intake":
        intake = cfg["docs"]["intake"]
        intake_low = {s.lower() for s in intake}
        vt = [t for t in cfg.get("validation_tab") or [] if t.lower() in intake_low]
        vt_low = {s.lower() for s in vt}
        for t in intake:
            if t != "What it is" and t.lower() not in vt_low:
                vt.append(t)
                vt_low.add(t.lower())
        cfg["validation_tab"] = vt
    return cfg


def set_validation_tab_subsections(config: dict[str, Any], titles: list[str]) -> dict[str, Any]:
    """Set which intake subsections appear on sec02 (Problem & validation)."""
    if not titles:
        raise ValueError("at least one subsection title required")
    cfg = _normalize_config(config)
    intake = subsections_for_doc(cfg, "intake")
    intake_low = {s.lower() for s in intake}
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in titles:
        title = _clean_title(raw)
        if not title or title.lower() in seen:
            continue
        if title == "What it is":
            continue
        if title.lower() not in intake_low:
            raise ValueError(
                f"subsection '{title}' not in intake list — add to intake first",
            )
        cleaned.append(title)
        seen.add(title.lower())
    if not cleaned:
        raise ValueError(
            "validation_tab needs at least one intake subsection (not 'What it is')",
        )
    cfg["validation_tab"] = cleaned
    return cfg


def add_doc_subsection(config: dict[str, Any], doc_key: str, title: str) -> dict[str, Any]:
    t = _clean_title(title)
    if not t:
        raise ValueError("subsection title required")
    cfg = _normalize_config(config)
    existing = list(subsections_for_doc(cfg, doc_key))
    if any(s.lower() == t.lower() for s in existing):
        return cfg
    existing.append(t)
    cfg["docs"][doc_key] = existing
    if doc_key == "intake" and t != "What it is":
        vt = list(validation_tab_subsections(cfg))
        if not any(s.lower() == t.lower() for s in vt):
            vt.append(t)
        cfg["validation_tab"] = vt
    return cfg