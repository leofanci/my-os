"""Guard: no real usage data in tracked files.

Repo is public. Real venture/profile/product/channel slugs live only in
the gitignored projects/ tree. This test collects those slugs at runtime
and fails if any tracked file mentions one. Fixture names must be generic
(demo, acme, profile-a).
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"

# Generic fixture slugs allowed in tracked files.
ALLOWED = {"demo", "acme", "acme-app", "profile-a", "profile-b", "acme-tiktok"}


def real_slugs():
    slugs = set()
    if not PROJECTS.is_dir():
        return slugs
    for proj in PROJECTS.iterdir():
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        slugs.add(proj.name)
        for kind in ("profiles", "products", "channels"):
            sub = proj / kind
            if sub.is_dir():
                slugs.update(p.name for p in sub.iterdir() if p.is_dir())
    return {s for s in slugs if s not in ALLOWED}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [f for f in out.splitlines() if f and not f.startswith("GTM OS.app/")]


class TestNoUsageData(unittest.TestCase):
    def test_tracked_files_contain_no_real_slugs(self):
        slugs = real_slugs()
        if not slugs:
            self.skipTest("no local projects/ data to guard against")
        pattern = re.compile(
            "|".join(re.escape(s) for s in sorted(slugs)), re.IGNORECASE
        )
        hits = []
        for rel in tracked_files():
            path = ROOT / rel
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                m = pattern.search(line)
                if m:
                    hits.append(f"{rel}:{i}: {m.group(0)}")
        self.assertEqual(
            hits, [],
            "Real usage-data slugs found in tracked files (repo is public):\n"
            + "\n".join(hits),
        )


if __name__ == "__main__":
    unittest.main()
