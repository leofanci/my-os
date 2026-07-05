import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestAiRules(unittest.TestCase):
    def test_chat_rail_has_single_brief_spec_path(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertEqual(CHAT_RAIL.count("update-brief-spec"), 2)
        self.assertNotIn("set-brief", CHAT_RAIL)
        self.assertNotIn("patch-brief", CHAT_RAIL)

    def test_chat_rail_has_tab_routing(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("Tab routing", CHAT_RAIL)
        self.assertIn("update-intake", CHAT_RAIL)
        self.assertIn("sec02", CHAT_RAIL)

    def test_chat_rail_has_write_gate(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("Write gate", CHAT_RAIL)
        self.assertIn("Tab routing", CHAT_RAIL)

    def test_chat_rail_has_skill_tagging(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("Skill tags", CHAT_RAIL)
        self.assertIn("/content-brief", CHAT_RAIL)

    def test_chat_rail_has_artifact_schemas(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("project_schemas.py", CHAT_RAIL)
        self.assertIn("core/subsections.py", CHAT_RAIL)
        self.assertIn("subsections.json", CHAT_RAIL)

    def test_claude_md_matches_write_table(self):
        from dashboard.ai_rules import WRITES_TABLE
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for line in WRITES_TABLE.strip().splitlines():
            if line.startswith("|") and "---" not in line:
                self.assertIn(line.strip(), claude, f"missing row: {line}")


if __name__ == "__main__":
    unittest.main()