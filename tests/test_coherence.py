"""Coherence — write gate, tab routing, and schema layout stay aligned."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestCoherence(unittest.TestCase):
    def test_chat_rail_has_write_gate(self):
        from dashboard.ai_rules import CHAT_RAIL

        self.assertIn("Write gate", CHAT_RAIL)
        self.assertIn("Propose", CHAT_RAIL)
        self.assertIn("Tab routing", CHAT_RAIL)
        self.assertIn("sec02", CHAT_RAIL)
        self.assertIn("save all tabs now", CHAT_RAIL)
        self.assertIn("Do not paste full memo", CHAT_RAIL)

    def test_memo_section_tabs_exist_in_layout(self):
        from core.ids import PROJECT_SECTION_LAYOUT
        from core.project_schemas import MEMO_SECTION

        layout_keys = set(PROJECT_SECTION_LAYOUT.keys())
        for mtype, tab in MEMO_SECTION.items():
            self.assertIn(tab, layout_keys, f"{mtype} → {tab} missing from PROJECT_SECTION_LAYOUT")

    def test_validation_intake_sections_subset(self):
        from core.project_schemas import INTAKE_SECTIONS, INTAKE_VALIDATION_TAB_SECTIONS

        for sec in INTAKE_VALIDATION_TAB_SECTIONS:
            self.assertIn(sec, INTAKE_SECTIONS)
        self.assertNotIn("What it is", INTAKE_VALIDATION_TAB_SECTIONS)

    def test_api_schemas_exports_validation_tab_sections(self):
        from core.project_schemas import INTAKE_VALIDATION_TAB_SECTIONS, schemas_for_api

        api = schemas_for_api()
        self.assertEqual(
            api["intake"]["validation_tab_sections"],
            list(INTAKE_VALIDATION_TAB_SECTIONS),
        )
        self.assertEqual(
            api["subsections"]["validation_tab_default"],
            list(INTAKE_VALIDATION_TAB_SECTIONS),
        )

    def test_subsection_defaults_single_source(self):
        from core.project_schemas import (
            INTAKE_SECTIONS,
            INTAKE_VALIDATION_TAB_SECTIONS,
            ROADMAP_SECTIONS,
            TECHNICAL_SECTIONS,
            schemas_for_api,
        )
        from core.subsections import DEFAULT_SUBSECTIONS, DEFAULT_VALIDATION_TAB

        api = schemas_for_api()
        for doc_key, canon in (
            ("intake", INTAKE_SECTIONS),
            ("technical", TECHNICAL_SECTIONS),
            ("roadmap", ROADMAP_SECTIONS),
        ):
            self.assertEqual(tuple(DEFAULT_SUBSECTIONS[doc_key]), canon)
            self.assertEqual(api[doc_key]["default_subsections"], list(canon))
            self.assertEqual(
                api["subsections"]["docs"][doc_key]["default_subsections"],
                list(canon),
            )
        self.assertEqual(DEFAULT_VALIDATION_TAB, INTAKE_VALIDATION_TAB_SECTIONS)

    def test_gtm_os_skill_lean_and_references_rail(self):
        skill = (ROOT / ".claude" / "skills" / "gtm-os" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("system prompt", skill.lower())
        self.assertIn("routing plan", skill.lower())
        self.assertIn("one tab per", skill.lower())
        self.assertLess(len(skill), 2200)

    def test_strategy_skills_reference_write_gate(self):
        skills_dir = ROOT / ".claude" / "skills"
        required = {
            "problem-validation", "venture-intake", "gtm-assessment", "positioning",
            "pricing-strategy", "experiment-design", "content-plan", "product-build",
        }
        for name in required:
            path = skills_dir / name / "SKILL.md"
            self.assertTrue(path.is_file(), f"missing skill {name}")
            body = path.read_text(encoding="utf-8")
            self.assertIn("Write gate", body, f"{name} missing Write gate section")

    def test_claude_md_references_write_gate(self):
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Write gate", claude)
        self.assertIn("TAB_ROUTING", claude)

    def test_os_ids_nav_keys_match_python_sections(self):
        from core.ids import PROJECT_SECTIONS

        js = (ROOT / "dashboard" / "os-ids.js").read_text(encoding="utf-8")
        self.assertIn("function sectionLayout", js)
        self.assertNotIn("PROJECT_SECTION_LAYOUT", js)
        for key, _label in PROJECT_SECTIONS:
            self.assertIn(f'key:"{key}"', js, f"{key} missing from PROJECT_SECTIONS nav")


if __name__ == "__main__":
    unittest.main()