"""Profile voices — projects/<project>/profiles/<profile>/voices/vc{N}.md

Same shape as core/brief_spec_util.py's brief-spec storage: several voices
per profile, each tagged with a platforms scope, selected explicitly, never
auto-matched. vc1 is the implicit default. Both modules delegate their
storage logic to core/numbered_profile_artifact.py.

Legacy migration: a profile's voice used to be profile.md's body. On first
touch, that body moves into voices/vc1.md (platforms: all) and profile.md
keeps only its frontmatter (name/topic/project).
"""
from pathlib import Path

from core.numbered_profile_artifact import NumberedArtifactStore, split_frontmatter

VOICE_DIR = "voices"
DEFAULT_VOICE_ID = "vc1"

_STORE = NumberedArtifactStore(dir_name=VOICE_DIR, id_prefix="vc")


def _migrate_legacy_voice(profile_dir: Path) -> None:
    """One-time move of profile.md's body into voices/vc1.md."""
    profile_md = profile_dir / "profile.md"
    voice_dir = profile_dir / VOICE_DIR
    if not profile_md.is_file() or voice_dir.is_dir():
        return
    fm, body = split_frontmatter(profile_md.read_text(encoding="utf-8"))
    if not body.strip():
        return
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "vc1.md").write_text(f"---\nplatforms: all\n---\n{body}\n", encoding="utf-8")
    fm_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    profile_md.write_text(f"---\n{fm_lines}\n---\n", encoding="utf-8")


def voice_file(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> Path:
    _migrate_legacy_voice(profile_dir)
    return _STORE.file(profile_dir, voice_id)


def read_voice_text(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    _migrate_legacy_voice(profile_dir)
    return _STORE.read_text(profile_dir, voice_id)


def read_voice_platforms(profile_dir: Path, voice_id: str = DEFAULT_VOICE_ID) -> str:
    _migrate_legacy_voice(profile_dir)
    return _STORE.read_platforms(profile_dir, voice_id)


def write_voice_text(profile_dir: Path, text: str, voice_id: str = DEFAULT_VOICE_ID,
                      platforms: str | None = None) -> None:
    _migrate_legacy_voice(profile_dir)
    _STORE.write_text(profile_dir, text, voice_id, platforms)


def list_voice_ids(profile_dir: Path) -> list[str]:
    _migrate_legacy_voice(profile_dir)
    return _STORE.list_ids(profile_dir)


def next_voice_id(profile_dir: Path) -> str:
    """Pure read — see brief_spec_util.next_brief_id for why this never
    reissues a deleted id."""
    _migrate_legacy_voice(profile_dir)
    return _STORE.next_id(profile_dir)


def delete_voice(profile_dir: Path, voice_id: str) -> None:
    _migrate_legacy_voice(profile_dir)
    _STORE.delete(profile_dir, voice_id, kind_label="voice")
