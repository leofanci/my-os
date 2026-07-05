"""Token budget guards — keep per-turn chat prompt lean."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# chars / 4 ≈ tokens (conservative for English prose)
def est_tokens(text: str) -> int:
    return len(text) // 4


class TestTokenBudget(unittest.TestCase):
    def test_chat_rail_under_budget(self):
        from dashboard.ai_rules import CHAT_RAIL

        chars = len(CHAT_RAIL)
        tok = est_tokens(CHAT_RAIL)
        self.assertLessEqual(chars, 7200, f"CHAT_RAIL bloated: {chars} chars (~{tok} tok)")
        self.assertLessEqual(tok, 1750, f"CHAT_RAIL over ~1750 tok guard: ~{tok} tok")
        self.assertGreater(chars, 4000, "CHAT_RAIL unexpectedly tiny — rules missing?")

    def test_no_duplicate_tab_tables_in_rail(self):
        from dashboard.ai_rules import CHAT_RAIL

        self.assertEqual(CHAT_RAIL.count("## Tab routing"), 1)
        self.assertNotIn("PROJECT_TABS", CHAT_RAIL)
        self.assertNotIn("Project left panel (six tabs", CHAT_RAIL)

    def test_gtm_os_skill_file_lean(self):
        skill = (ROOT / ".claude" / "skills" / "gtm-os" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(skill), 2200, f"gtm-os SKILL.md should stay lean: {len(skill)} chars")

    def test_gtm_os_injected_stub_not_full_skill(self):
        from dashboard.server import _RAIL_COVERED_SKILL_STUBS, _load_skill_body

        self.assertIn("gtm-os", _RAIL_COVERED_SKILL_STUBS)
        body = _load_skill_body("gtm-os")
        self.assertLess(len(body), 400, "gtm-os injection should be stub-sized")
        self.assertIn("system prompt", body.lower())

    def test_write_gate_forbids_chat_body_dup(self):
        from dashboard.ai_rules import CHAT_RAIL

        self.assertIn("Do not paste full memo", CHAT_RAIL)
        self.assertIn("never echo", CHAT_RAIL.lower())

    def test_state_snapshot_is_index_only(self):
        from dashboard.server import state_snapshot
        import dashboard.db as db
        import index

        root = ROOT
        prev_db = db.DB_PATH
        try:
            db.DB_PATH = root / "database" / "data" / "os.db"
            if not db.db_exists():
                index.build(root)
            snap = state_snapshot(db.tree())
        finally:
            db.DB_PATH = prev_db
        self.assertIn("index only", snap.lower())
        self.assertLess(len(snap), 4000, f"state_snapshot too large: {len(snap)} chars")


if __name__ == "__main__":
    unittest.main()