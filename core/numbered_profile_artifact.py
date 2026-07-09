"""Shared machinery for a profile artifact numbered N1/N2/... (brief-specs'
br1/br2/... and voices' vc1/vc2/...): frontmatter parsing, the per-directory
.max_id marker that mints never-reused numbers, and read/write/list/delete.

core/brief_spec_util.py and core/voice_util.py are thin configuration
wrappers around one NumberedArtifactStore each — same logic, parameterized
by directory name and id prefix. Legacy-migration (each has a different
pre-migration shape: a dedicated file vs. profile.md's body) stays in each
of those modules rather than here.
"""
import re
from pathlib import Path

_MARKER_FILE = ".max_id"


def split_frontmatter(text: str) -> tuple[dict, str]:
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


class NumberedArtifactStore:
    """One instance per artifact kind — e.g. NumberedArtifactStore("brief-specs", "br")."""

    def __init__(self, dir_name: str, id_prefix: str):
        self.dir_name = dir_name
        self.id_prefix = id_prefix
        self.default_id = f"{id_prefix}1"
        self._id_re = re.compile(rf"^{re.escape(id_prefix)}(\d+)\.md$")

    def _read_marker(self, art_dir: Path) -> int:
        f = art_dir / _MARKER_FILE
        if f.is_file():
            try:
                return int(f.read_text(encoding="utf-8").strip())
            except ValueError:
                pass
        return 0

    def _bump_marker(self, art_dir: Path, n: int) -> None:
        """High-water mark of every id ever minted — never moves backward, so
        a deleted id (whose file is gone) still can't be reissued."""
        if n > self._read_marker(art_dir):
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / _MARKER_FILE).write_text(str(n), encoding="utf-8")

    def file(self, profile_dir: Path, artifact_id: str | None = None) -> Path:
        return profile_dir / self.dir_name / f"{artifact_id or self.default_id}.md"

    def read_text(self, profile_dir: Path, artifact_id: str | None = None) -> str:
        f = self.file(profile_dir, artifact_id)
        if not f.exists():
            return ""
        _, body = split_frontmatter(f.read_text(encoding="utf-8"))
        return body

    def read_platforms(self, profile_dir: Path, artifact_id: str | None = None) -> str:
        f = self.file(profile_dir, artifact_id)
        if not f.exists():
            return "all"
        fm, _ = split_frontmatter(f.read_text(encoding="utf-8"))
        return fm.get("platforms", "all")

    def write_text(self, profile_dir: Path, text: str, artifact_id: str | None = None,
                    platforms: str | None = None) -> None:
        """platforms=None keeps whatever tag it already had (or "all" for a
        brand new one) — an update without --platforms must not reset the tag."""
        f = self.file(profile_dir, artifact_id)
        f.parent.mkdir(parents=True, exist_ok=True)
        if platforms is None:
            platforms = self.read_platforms(profile_dir, artifact_id) if f.exists() else "all"
        body = (text or "").strip()
        f.write_text(f"---\nplatforms: {platforms}\n---\n{body}\n", encoding="utf-8")
        m = self._id_re.match(f.name)
        if m:
            self._bump_marker(f.parent, int(m.group(1)))

    def list_ids(self, profile_dir: Path) -> list[str]:
        """Every id for this profile — 1 (the default) is always included
        even if nobody has written to it yet."""
        nums = {1}
        d = profile_dir / self.dir_name
        if d.is_dir():
            for f in d.iterdir():
                m = self._id_re.match(f.name)
                if m:
                    nums.add(int(m.group(1)))
        return [f"{self.id_prefix}{n}" for n in sorted(nums)]

    def next_id(self, profile_dir: Path) -> str:
        """Pure read — does not itself reserve anything (that happens when
        the caller actually writes the file). Never reissues a deleted id."""
        d = profile_dir / self.dir_name
        nums = {1, self._read_marker(d)}
        if d.is_dir():
            for f in d.iterdir():
                m = self._id_re.match(f.name)
                if m:
                    nums.add(int(m.group(1)))
        return f"{self.id_prefix}{max(nums) + 1}"

    def delete(self, profile_dir: Path, artifact_id: str, *, kind_label: str) -> None:
        if artifact_id == self.default_id:
            # The default id is permanent — list_ids() always reports it
            # whether or not a file exists, so "deleting" it would silently
            # reappear on the next list. Clear its content instead.
            raise ValueError(f"cannot delete {self.default_id} — it's the permanent default; clear its text instead")
        ids = self.list_ids(profile_dir)
        if len(ids) <= 1:
            raise ValueError(f"cannot delete the only remaining {kind_label}")
        if artifact_id not in ids:
            raise ValueError(f"{kind_label} '{artifact_id}' not found")
        f = profile_dir / self.dir_name / f"{artifact_id}.md"
        if f.exists():
            f.unlink()
