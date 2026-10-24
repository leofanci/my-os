import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestAiRules(unittest.TestCase):
    def test_chat_rail_has_single_brief_spec_path(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertEqual(CHAT_RAIL.count("update-brief-spec"), 2)
        self.assertNotIn("set-brief", CHAT_RAIL)
        self.assertNotIn("patch-brief", CHAT_RAIL)

    def test_chat_rail_is_deliverables_not_tabs(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("## Deliverables", CHAT_RAIL)
        self.assertIn("update-intake", CHAT_RAIL)
        self.assertNotIn("## Tab routing", CHAT_RAIL)
        self.assertNotIn("| sec02 |", CHAT_RAIL)   # no tab table; ids only as lookup examples

    def test_chat_rail_has_approval_and_teammate_voice(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("## Approval before every save", CHAT_RAIL)
        self.assertIn("APPROVAL:", CHAT_RAIL)
        self.assertIn("## How you work and talk", CHAT_RAIL)

    def test_terminal_rules_keep_tab_vocabulary(self):
        from dashboard.ai_rules import TERMINAL_RULES
        self.assertIn("Tab routing", TERMINAL_RULES)
        self.assertIn("Write gate", TERMINAL_RULES)

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