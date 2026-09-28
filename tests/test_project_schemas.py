import json
import tempfile
import unittest
from pathlib import Path

from core.project_schemas import (
    INTAKE_SECTIONS,
    INTAKE_STARTER,
    ROADMAP_SECTIONS,
    normalize_experiment_body,
    normalize_intake,
    normalize_memo_body,
    normalize_roadmap,
    schemas_for_api,
)


class TestProjectSchemas(unittest.TestCase):
    def test_intake_starter_has_all_sections(self):
        for sec in INTAKE_SECTIONS:
            self.assertIn(f"## {sec}", INTAKE_STARTER)

    def test_normalize_intake_reorders_and_fills_gaps(self):
        raw = """# Venture intake

## Evidence log
- 2026-01-01: first signal

## What it is
B2B SaaS widget.

## Stage & evidence
Idea stage.
"""
        out = normalize_intake(raw)
        self.assertTrue(out.startswith("# Venture intake\n"))
        idx_what = out.index("## What it is")
        idx_stage = out.index("## Stage & evidence")
        idx_market = out.index("## Market")
        idx_evidence = out.index("## Evidence log")
        self.assertLess(idx_what, idx_stage)
        self.assertLess(idx_stage, idx_market)
        self.assertLess(idx_market, idx_evidence)
        self.assertIn("B2B SaaS widget.", out)
        self.assertIn("first signal", out)
        self.assertIn("## Resources", out)

    def test_normalize_memo_problem_validation_coerces_evidence_lines(self):
        body = normalize_memo_body("problem-validation", {
            "problem_statement": "Pain",
            "evidence": "interview note one\ninterview note two",
            "severity": "PAINKILLER",
            "version": 2,
        }, version=2)
        self.assertEqual(body["version"], 2)
        self.assertEqual(body["severity"], "painkiller")
        self.assertEqual(len(body["evidence"]), 2)
        self.assertEqual(body["evidence"][0]["signal"], "interview note one")
        self.assertNotIn("extra_field", body)

    def test_normalize_memo_drops_unknown_keys(self):
        body = normalize_memo_body("positioning", {
            "summary": "One-liner test",
            "recommendation": "Go",
            "category_options": ["should be dropped"],
        })
        self.assertEqual(body["summary"], "One-liner test")
        self.assertNotIn("category_options", body)

    def test_normalize_experiment_syncs_assumption_fields(self):
        body = normalize_experiment_body({
            "assumption": "Users pay",
            "success_criteria": "5/10",
        })
        self.assertEqual(body["assumption"], "Users pay")
        self.assertEqual(body["assumption_under_test"], "Users pay")

    def test_normalize_roadmap_canonical_sections(self):
        raw = """# Roadmap

## Shipped
- [x] Old thing

## Next
- [ ] New thing
"""
        out = normalize_roadmap(raw)
        for sec in ROADMAP_SECTIONS:
            self.assertIn(f"## {sec}", out)
        self.assertLess(out.index("## Now"), out.index("## Next"))
        self.assertIn("New thing", out)

    def test_schemas_for_api_matches_memo_types(self):
        api = schemas_for_api()
        self.assertIn("problem-validation", api["memos"])
        self.assertTrue(api["memos"]["problem-validation"])
        self.assertEqual(api["intake"]["sections"], list(INTAKE_SECTIONS))

    def test_manual_and_osctl_memo_same_shape(self):
        manual = normalize_memo_body("problem-validation", {
            "problem_statement": "X",
            "who_has_it": "Y",
            "recommendation": "validate",
        }, version=1)
        osctl = normalize_memo_body("problem-validation", json.loads(json.dumps({
            "problem_statement": "X",
            "who_has_it": "Y",
            "recommendation": "validate",
        })), version=1)
        self.assertEqual(manual.keys(), osctl.keys())


if __name__ == "__main__":
    unittest.main()