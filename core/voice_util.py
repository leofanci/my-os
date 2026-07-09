"""Profile voices — projects/<project>/profiles/<profile>/voices/vc{N}.md

Same shape as core/brief_spec_util.py's brief-spec storage: several voices
per profile, each tagged with a platforms scope, selected explicitly, never
auto-matched. vc1 is the implicit default.

Legacy migration: a profile's voice used to be profile.md's body. On first
touch, that body moves into voices/vc1.md (platforms: all) and profile.md
keeps only its frontmatter (name/topic/project).
"""
import re
from pathlib import Path

VOICE_DIR = "voices"
DEFAULT_VOICE_ID = "vc1"
_VC_RE = re.compile(r"^vc(\d+)\.md$")
_MARKER_FILE = ".max_id"


def _read_marker(voice_dir: Path) -> int:
    f = voice_dir / _MARKER_FILE
    if f.is_file():
        try:
            return int(f.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return 0


def _bump_marker(voice_dir: Path, n: int) -> None:
    """High-water mark of every vc id ever minted — never moves backward, so
    a deleted id (whose file is gone) still can't be reissued."""
    if n > _read_marker(voice_dir):
        voice_dir.mkdir(parents=True, exist_ok=True)
        (voice_dir / _MARKER_FILE).write_text(str(n), encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = {}
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            return fm, parts[2].strip()
    return {}, text.strip()


def _migrate_legacy_voice(profile_dir: Path) -> None:
    """One-time move of profile.md's body into voices/vc1.md."""
    profile_md = profile_dir / "profile.md"
    voice_dir = profile_dir / VOICE_DIR
    if not profile_md.is_file() or voice_dir.is_dir():
        return
    fm, body = _split_frontmatter(profile_md.read_text(encoding="utf-8"))
    if not body.strip():
        return
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "vc1.md").write_text(f"---\nplatforms: all\n---\n{body}\n", encoding="utf-8")
    fm_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    profile_md.write_text(f"---\n{fm_lines}\n---\n", encoding="utf-8")


def voice_file(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> Path:
    _migrate_legacy_voice(profile_dir)
    return profile_dir / VOICE_DIR / f"{voice_id}.md"


def read_voice_text(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    f = voice_file(profile_dir, voice_id)
    if not f.exists():
        return ""
    _, body = _split_frontmatter(f.read_text(encoding="utf-8"))
    return body


def read_voice_platforms(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    f = voice_file(profile_dir, voice_id)
    if not f.exists():
        return "all"
    fm, _ = _split_frontmatter(f.read_text(encoding="utf-8"))
    return fm.get("platforms", "all")


def write_voice_text(profile_dir: Path, text: str, voice_id: str = DEFAULT_VOICE_ID,
                      platforms: str | None = None) -> None:
    f = voice_file(profile_dir, voice_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    if platforms is None:
        platforms = read_voice_platforms(profile_dir, voice_id) if f.exists() else "all"
    body = (text or "").strip()
    f.write_text(f"---\nplatforms: {platforms}\n---\n{body}\n", encoding="utf-8")
    m = _VC_RE.match(f.name)
    if m:
        _bump_marker(f.parent, int(m.group(1)))


def list_voice_ids(profile_dir: Path) -> list[str]:
    _migrate_legacy_voice(profile_dir)
    nums = {1}
    d = profile_dir / VOICE_DIR
    if d.is_dir():
        for f in d.iterdir():
            m = _VC_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return [f"vc{n}" for n in sorted(nums)]


def next_voice_id(profile_dir: Path) -> str:
    """Pure read — see brief_spec_util.next_brief_id for why this never
    reissues a deleted id."""
    _migrate_legacy_voice(profile_dir)
    d = profile_dir / VOICE_DIR
    nums = {1, _read_marker(d)}
    if d.is_dir():
        for f in d.iterdir():
            m = _VC_RE.match(f.name)
            if m:
                nums.add(int(m.group(1)))
    return f"vc{max(nums) + 1}"


def delete_voice(profile_dir: Path, voice_id: str) -> None:
    if voice_id == DEFAULT_VOICE_ID:
        # vc1 is the permanent default slot — list_voice_ids() always reports
        # it whether or not a file exists, so "deleting" it would silently
        # reappear on the next list. Clear its content via write_voice_text
        # instead of deleting it structurally.
        raise ValueError(f"cannot delete {DEFAULT_VOICE_ID} — it's the permanent default; clear its text instead")
    ids = list_voice_ids(profile_dir)
    if len(ids) <= 1:
        raise ValueError("cannot delete the only remaining voice")
    if voice_id not in ids:
        raise ValueError(f"voice '{voice_id}' not found")
    f = profile_dir / VOICE_DIR / f"{voice_id}.md"
    if f.exists():
        f.unlink()
