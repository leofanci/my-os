import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "dashboard" / "app.js"


class TestProfileFilterPersistence(unittest.TestCase):
    def test_selected_filter_survives_profile_rerender(self):
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("const PROFILE_FILTER = {};", source)
        self.assertRegex(
            source,
            r'let FILTER\s*=\s*PROFILE_FILTER\[slug\]\s*\|\|\s*"scheduled";',
        )
        self.assertIn('PROFILE_FILTER[slug] = FILTER;', source)
        self.assertIn(
            'class="chip${FILTER==="unscheduled"?" on":""}" data-f="unscheduled"',
            source,
        )
        self.assertNotIn('let FILTER = "scheduled";', source)


if __name__ == "__main__":
    unittest.main()
