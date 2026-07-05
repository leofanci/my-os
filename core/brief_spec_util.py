"""Profile brief-spec.md — single source of truth for all brief generation.

Every path (dashboard button, chat, terminal, validation) reads/writes the same
file: projects/<project>/profiles/<profile>/brief-spec.md
"""
import re
from pathlib import Path

SPEC_FILENAME = "brief-spec.md"


def spec_file(profile_dir: Path) -> Path:
    return profile_dir / SPEC_FILENAME


def read_spec_text(profile_dir: Path) -> str:
    """Load the live brief spec from disk (always read at job time — never cache)."""
    f = spec_file(profile_dir)
    return f.read_text(encoding="utf-8") if f.exists() else ""


def write_spec_text(profile_dir: Path, text: str) -> None:
    """Persist brief spec — same file Profile Setup and update-brief-spec write."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    spec_file(profile_dir).write_text((text or "").strip() + "\n", encoding="utf-8")


def format_for_brief_prompt(spec_text: str) -> str:
    """Block injected into prompts/brief.txt as {{PROFILE_BRIEF_SPEC}}."""
    spec_text = (spec_text or "").strip()
    if not spec_text:
        return "(no per-field overrides — use your best judgment for the content type and platform)"
    return (
        "--- PROFILE BRIEF SPEC (per-field rules — override defaults below) ---\n"
        f"{spec_text}\n"
        "--- END PROFILE BRIEF SPEC ---"
    )


def format_for_plan_prompt(spec_text: str) -> str:
    spec_text = (spec_text or "").strip()
    if not spec_text:
        return ""
    return (
        "\n--- PROFILE BRIEF SPEC (how posts are produced — plan accordingly) ---\n"
        f"{spec_text}\n"
    )

# Always required on every brief (see prompts/brief.txt).
IDENTITY_FIELDS = ("id", "channels", "platform", "format", "objective", "pillar")
# Slot fields write_brief may copy only when the profile spec's JSON template lists them.
SLOT_FILL_FIELDS = ("platform", "format", "objective", "pillar")

# Prose words that sometimes appear as `word:` headings in specs — not JSON fields.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at", "by",
    "max", "min", "use", "not", "per", "each", "all", "one", "example", "rules",
    "rule", "must", "should", "never", "always", "eg", "etc", "vs", "if", "when",
    "with", "from", "into", "between", "both", "any", "every", "required",
    "optional", "field", "fields", "profile", "brief", "spec", "voice", "note",
    "notes", "output", "section", "sections", "slides",
})

# Keys inside slide_overlays items — not top-level brief fields.
_NESTED_SLIDE_KEYS = frozenset({"slide", "overlay"})

_JSON_KEY_RE = re.compile(r'"([a-z][a-z0-9_]*)"')
_TOP_LEVEL_JSON_KEY_RE = re.compile(r'^  "([a-z][a-z0-9_]*)"', re.MULTILINE)
_FIELD_ALIASES = {"slides": "slide_overlays"}
_BACKTICK_RE = re.compile(r"`([a-z][a-z0-9_]*)`")
_BULLET_RE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?([a-z][a-z0-9_]*)(?:\*\*)?(?:\s*[:(]|$)",
    re.MULTILINE,
)
_COLON_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*:", re.MULTILINE)
_EM_RULE_RE = re.compile(
    r"^\s*[—–-]\s*(?:\*\*)?([a-z][a-z0-9_]*)(?:\*\*)?\s*:",
    re.MULTILINE,
)
_DECLARED_KEYS_RE = re.compile(
    r"exactly these keys[^:\n]*:\s*([^\n]+)",
    re.I,
)


def _normalize_spec_quotes(spec_text: str) -> str:
    return (spec_text or "").replace("\u201c", '"').replace("\u201d", '"')


def _is_identifier(name: str) -> bool:
    return len(name) >= 2 and bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


def _declared_key_list(spec_text: str) -> list[str]:
    """Parse 'exactly these keys: id, title, …' comma lists in prose specs."""
    m = _DECLARED_KEYS_RE.search(spec_text or "")
    if not m:
        return []
    out = []
    for part in m.group(1).split(","):
        name = part.strip().rstrip(".")
        if _is_identifier(name):
            out.append(name)
    return out


def _top_level_json_keys(spec_text: str) -> list[str]:
    text = _normalize_spec_quotes(spec_text)
    seen, out = set(), []
    for m in _TOP_LEVEL_JSON_KEY_RE.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _accept(name: str, *, strict: bool) -> bool:
    if name in _NESTED_SLIDE_KEYS:
        return False
    if name in IDENTITY_FIELDS or not _is_identifier(name):
        return False
    # Underscore names are almost always real fields (cover_overlay, catchy_title).
    if "_" in name:
        return True
    if strict and name in _STOPWORDS:
        return False
    return True


def parse_spec_fields(spec_text: str) -> list[str]:
    """Return ordered unique content field names declared in a brief spec."""
    spec_text = _normalize_spec_quotes(spec_text)
    if not spec_text.strip():
        return []
    top = [k for k in _top_level_json_keys(spec_text)
           if k not in ("id",) and k not in IDENTITY_FIELDS]
    if top:
        return top
    declared = [k for k in _declared_key_list(spec_text)
                if k not in ("id",) and k not in IDENTITY_FIELDS]
    if declared:
        return declared
    seen, out = set(), []
    for rx, strict in (
        (_JSON_KEY_RE, False),
        (_BACKTICK_RE, False),
        (_EM_RULE_RE, True),
        (_BULLET_RE, True),
        (_COLON_RE, True),
    ):
        for m in rx.finditer(spec_text):
            name = m.group(1)
            if not _accept(name, strict=strict) or name in seen:
                continue
            seen.add(name)
            out.append(name)
    return out


def _json_keys_in_spec(spec_text: str) -> set[str]:
    spec_text = _normalize_spec_quotes(spec_text)
    top = _top_level_json_keys(spec_text)
    if top:
        return set(top)
    declared = _declared_key_list(spec_text)
    if declared:
        return set(declared)
    return {m.group(1) for m in _JSON_KEY_RE.finditer(spec_text)}


def _sentence_case(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return text
    words = text.split()
    first = words[0]
    if len(first) >= 2 and len(first) <= 4 and first.isupper() and first.isalpha():
        rest = " ".join(words[1:]).lower()
        return f"{first} {rest}".strip() if rest else first
    return text[0].upper() + text[1:].lower()


def normalize_brief_for_spec(brief: dict, spec_text: str) -> None:
    """In-place: map legacy field names (e.g. slides) to spec names."""
    if not isinstance(brief, dict):
        return
    spec_text = spec_text or ""
    wanted = set(parse_spec_fields(spec_text))
    for old, new in _FIELD_ALIASES.items():
        if new in wanted and old in brief and new not in brief:
            brief[new] = brief.pop(old)
    if "cover_overlay" in wanted and isinstance(brief.get("cover_overlay"), str):
        if "sentence case" in spec_text.lower():
            brief["cover_overlay"] = _sentence_case(brief["cover_overlay"])


def merge_fields_from_slot(spec_text: str) -> tuple[str, ...]:
    """Slot fields to copy into a brief when the model omitted them."""
    if not (spec_text or "").strip():
        return ("channels",) + SLOT_FILL_FIELDS
    keys = _json_keys_in_spec(spec_text)
    out = ["channels"]
    out.extend(k for k in SLOT_FILL_FIELDS if k in keys)
    return tuple(out)


def allowed_brief_keys(spec_text: str) -> set[str] | None:
    """Allowed brief keys for a profile spec. None = legacy (no restriction)."""
    if not (spec_text or "").strip():
        return None
    keys = _json_keys_in_spec(spec_text)
    allowed = {"id", "channels"} | set(parse_spec_fields(spec_text))
    allowed.update(k for k in SLOT_FILL_FIELDS if k in keys)
    return allowed


def _field_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _spec_omits_channels(spec_text: str) -> bool:
    """True when the profile spec forbids channels on model brief output."""
    return bool(re.search(r"NO channels", spec_text or "", re.I))


_VIDEO_FORMATS = frozenset({"reel", "video", "short"})
_CAROUSEL_DEFAULT = "carousel"


def slot_format(slot: dict | None) -> str:
    """Resolved output format for a plan slot (carousel unless explicitly video)."""
    return ((slot or {}).get("format") or _CAROUSEL_DEFAULT).lower()


def _is_video_slot(slot: dict) -> bool:
    return slot_format(slot) in _VIDEO_FORMATS


def _field_optional_for_slot(key: str, spec_text: str, slot: dict) -> bool:
    """Fields declared carousel-only or video-only in the spec may be omitted per slot format."""
    spec = spec_text or ""
    if key == "catchy_title" and re.search(r"catchy_title:\s*carousel only", spec, re.I):
        return _is_video_slot(slot)
    if key == "overlay" and re.search(
        r"overlay:.*(?:video/reel only|reel only)|omit.*carousel", spec, re.I
    ):
        return not _is_video_slot(slot)
    if key == "slide_overlays" and re.search(
        r"slide_overlays:.*carousel only|omit.*(?:video|reel)", spec, re.I
    ):
        return _is_video_slot(slot)
    return False


def _carousel_slide_bounds(spec_text: str) -> tuple[int, int]:
    """Parse min/max carousel slide count from profile brief-spec (default 8–10)."""
    spec = spec_text or ""
    m = re.search(r"max\s+(\d+)\s+slides?", spec, re.I)
    if m:
        hi = int(m.group(1))
        return (1, hi)
    for pat in (
        r"one entry per slide\s*\((\d+)\s*[–-]\s*(\d+)\)",
        r"carousel[^.\n]*\((\d+)\s*[–-]\s*(\d+)\s+slides?\)",
        r"(\d+)\s*[–-]\s*(\d+)\s+slides?",
        r"gen_prompts:.*?\((\d+)\s*[–-]\s*(\d+)",
    ):
        m = re.search(pat, spec, re.I)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return (lo, hi)
    return (8, 10)


def _validate_slide_overlays(obj: dict, spec_text: str, slot: dict) -> list[str]:
    if "slide_overlays" not in parse_spec_fields(spec_text or ""):
        return []
    if _is_video_slot(slot):
        return []
    lo, hi = _carousel_slide_bounds(spec_text)
    slides = obj.get("slide_overlays")
    if not isinstance(slides, list) or not slides:
        return ["slide_overlays must be a non-empty array for carousel"]
    n = len(slides)
    if n < lo or n > hi:
        return [f"carousel slot requires {lo}-{hi} slide_overlays (got {n})"]
    for i, item in enumerate(slides, 1):
        if not isinstance(item, dict):
            return [f"slide_overlays[{i - 1}] must be an object"]
        if _field_empty(item.get("overlay")):
            slide_n = item.get("slide") or i
            return [f"slide_overlays slide {slide_n} missing overlay text"]
    prompts = obj.get("gen_prompts")
    if isinstance(prompts, list) and prompts and len(prompts) != n:
        return [f"slide_overlays count ({n}) must match gen_prompts count ({len(prompts)})"]
    return []


def _validate_gen_prompts(obj: dict, spec_text: str, slot: dict) -> list[str]:
    if "gen_prompts" not in parse_spec_fields(spec_text or ""):
        return []
    prompts = obj.get("gen_prompts")
    if not isinstance(prompts, list) or not prompts:
        return ["gen_prompts must be a non-empty array"]
    n = len(prompts)
    if _is_video_slot(slot):
        if n != 1:
            return [f"video/reel slot requires exactly 1 gen_prompt (got {n})"]
    else:
        lo, hi = _carousel_slide_bounds(spec_text)
        if n < lo or n > hi:
            return [f"carousel slot requires {lo}-{hi} gen_prompts (got {n})"]
    return []


def validate_brief_obj(obj, slot_id: str, spec_text: str = "", slot: dict | None = None,
                       *, strict_spec: bool = True) -> list[str]:
    """Validate a brief dict.

    strict_spec=True  → new briefs must match current brief-spec.md.
    strict_spec=False → existing briefs grandfathered (spec changes do not
                        force old posts to conform); only core identity checked.
    """
    if not isinstance(obj, dict):
        return ["brief is not a JSON object"]
    slot = slot or {}
    errs = []
    if obj.get("id") and obj["id"] != slot_id:
        errs.append(f"brief id '{obj.get('id')}' != slot id '{slot_id}'")
    if _field_empty(obj.get("channels")) and not _spec_omits_channels(spec_text):
        errs.append("missing required field 'channels'")
    if strict_spec:
        for key in parse_spec_fields(spec_text or ""):
            if _field_optional_for_slot(key, spec_text, slot):
                continue
            if _field_empty(obj.get(key)):
                errs.append(f"missing spec field '{key}'")
        errs.extend(_validate_slide_overlays(obj, spec_text, slot))
        errs.extend(_validate_gen_prompts(obj, spec_text, slot))
    return errs