"""Guard: no two things ever share one composed id.

A composed id (pr1.pf1.sec00.po3, ...) is meant to be the one permanent
reference to a single thing. Posts are the one kind minted from a bare
counter with content baked straight into plan files (see mint_post_ids),
so they're the kind that can drift and collide without anyone noticing —
this is what actually happened on 2026-07-06 (two posts sharing po3, one
resolving via the SQLite index, the other via file lookup). Every other
kind is allocated from a natural key, so IdRegistry.build() raising
ValueError is itself the guard for those.
"""
import unittest
from pathlib import Path

from core.ids import find_duplicate_ids, find_duplicate_post_ids

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"


class TestNoDuplicateIds(unittest.TestCase):
    def test_no_duplicate_post_ids_in_plan_files(self):
        if not PROJECTS.is_dir():
            self.skipTest("no local projects/ data to guard against")
        dupes = find_duplicate_post_ids(ROOT)
        self.assertEqual(
            dupes, {},
            "Two or more posts share the same composed id:\n"
            + "\n".join(f"  {pid}: {files}" for pid, files in dupes.items()),
        )

    def test_no_duplicate_ids_across_any_kind(self):
        if not PROJECTS.is_dir():
            self.skipTest("no local projects/ data to guard against")
        from dashboard import db  # noqa: WPS433 — heavy import, keep local to the test

        # Other test modules monkeypatch db.DB_PATH to a throwaway temp dir
        # for isolation and don't all restore it — pin it back to the real
        # workspace db so this test isn't at the mercy of run order.
        real_db_path = ROOT / "database" / "data" / "os.db"
        prior_db_path = db.DB_PATH
        db.DB_PATH = real_db_path
        try:
            problems = find_duplicate_ids(ROOT, db.tree(), db.posts())
        finally:
            db.DB_PATH = prior_db_path
        self.assertEqual(
            problems, [],
            "Duplicate composed id(s) detected:\n" + "\n".join(problems),
        )


if __name__ == "__main__":
    unittest.main()
