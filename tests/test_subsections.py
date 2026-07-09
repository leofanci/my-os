import json
import tempfile
import unittest
from pathlib import Path

from core.subsections import (
    CONFIG_FILENAME,
    add_doc_subsection,
    default_config,
    ensure_config,
    load_config,
    merge_headings_into_config,
    normalize_doc_text,
    save_config,
    set_doc_subsections,
    set_validation_tab_subsections,
    starter_text,
    subsections_for_doc,
    validation_tab_subsections,
)


class TestSubsections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "projects" / "acme"
        self.proj.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_config_matches_legacy_sections(self):
        cfg = default_config()
        self.assertEqual(len(cfg["docs"]["intake"]), 6)
        self.assertEqual(len(cfg["docs"]["technical"]), 7)
        self.assertNotIn("What it is", cfg["validation_tab"])

    def test_ensure_config_writes_file(self):
        cfg = ensure_config(self.root, "acme")
        path = self.proj / CONFIG_FILENAME
        self.assertTrue(path.is_file())
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["docs"]["technical"], cfg["docs"]["technical"])

    def test_read_subsections_via_fileops_ensures_file(self):
        import dashboard.fileops as fileops

        fileops.ROOT = self.root
        payload = fileops.read_subsections("acme")
        self.assertTrue((self.proj / CONFIG_FILENAME).is_file())
        self.assertIn("docs", payload)
        self.assertIn("roadmap", payload["docs"])

    def test_custom_technical_subsections_normalize_and_persist(self):
        cfg = set_doc_subsections(default_config(), "technical", ["Stack", "Prompt", "Tools"])
        save_config(self.root, "acme", cfg)
        raw = """# Technical

## Tools
MCP servers.

## Stack
Python 3.12.

## Prompt
System prompt v2.
"""
        out, updated = normalize_doc_text(raw, doc_key="technical", config=load_config(self.root, "acme"))
        self.assertIn("## Prompt", out)
        self.assertIn("MCP servers", out)
        self.assertEqual(
            list(subsections_for_doc(updated, "technical")),
            ["Stack", "Prompt", "Tools"],
        )
        save_config(self.root, "acme", updated)
        reloaded = load_config(self.root, "acme")
        self.assertEqual(reloaded["docs"]["technical"], ["Stack", "Prompt", "Tools"])

    def test_merge_headings_appends_unknown_from_manual_edit(self):
        cfg = default_config()
        raw = """# Technical

## Stack
Py

## Custom lane
Hand-added.
"""
        merged = merge_headings_into_config(cfg, "technical", raw)
        self.assertIn("Custom lane", merged["docs"]["technical"])
        out, updated = normalize_doc_text(raw, doc_key="technical", config=merged)
        self.assertIn("## Custom lane", out)
        self.assertIn("Hand-added", out)

    def test_add_subsection_extends_list(self):
        cfg = add_doc_subsection(default_config(), "technical", "Prompt")
        self.assertIn("Prompt", cfg["docs"]["technical"])

    def test_intake_validation_tab_gains_new_subsection(self):
        cfg = add_doc_subsection(default_config(), "intake", "Beachhead")
        self.assertIn("Beachhead", cfg["validation_tab"])
        self.assertNotIn("What it is", cfg["validation_tab"])

    def test_starter_uses_project_subsections(self):
        cfg = set_doc_subsections(default_config(), "technical", ["Stack", "Prompt"])
        starter = starter_text(cfg, "technical")
        self.assertIn("## Stack", starter)
        self.assertIn("## Prompt", starter)
        self.assertNotIn("## Architecture", starter)

    def test_validation_tab_subsections_respects_config(self):
        cfg = default_config()
        cfg["validation_tab"] = ["Stage & evidence", "Market"]
        self.assertEqual(validation_tab_subsections(cfg), ("Stage & evidence", "Market"))

    def test_set_validation_tab_subsections_subset_of_intake(self):
        cfg = set_validation_tab_subsections(default_config(), ["Market", "Goals"])
        self.assertEqual(cfg["validation_tab"], ["Market", "Goals"])
        self.assertNotIn("What it is", cfg["validation_tab"])

    def test_set_validation_tab_rejects_unknown_intake_title(self):
        with self.assertRaises(ValueError):
            set_validation_tab_subsections(default_config(), ["Beachhead"])

    def test_intake_normalize_does_not_expand_explicit_validation_tab(self):
        cfg = set_validation_tab_subsections(default_config(), ["Stage & evidence", "Market"])
        raw = """# Venture intake

## What it is
One line.

## Stage & evidence
Idea.

## Market
TAM note.

## Resources

## Goals

## Evidence log
"""
        _, updated = normalize_doc_text(raw, doc_key="intake", config=cfg)
        self.assertEqual(updated["validation_tab"], ["Stage & evidence", "Market"])

    def test_update_doc_section_patches_one_heading(self):
        import dashboard.fileops as fileops

        fileops.ROOT = self.root
        cfg = ensure_config(self.root, "acme")
        path = self.proj / "technical.md"
        path.write_text(starter_text(cfg, "technical"), encoding="utf-8")
        out = fileops.update_doc_section("acme", "technical", "Stack", "- RN\n- Postgres")
        self.assertEqual(out["title"], "Stack")
        text = path.read_text(encoding="utf-8")
        self.assertIn("RN", text)
        self.assertIn("## Architecture", text)


if __name__ == "__main__":
    unittest.main()