"""Chat topic follows the thread + @tags, not whichever dashboard tab is open."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _deixis_source():
    m = re.search(r"const VIEW_DEIXIS_RE = (/.+/[a-z]*);\n", APP_JS)
    assert m, "VIEW_DEIXIS_RE missing from app.js"
    return m.group(1)


class TestChatViewContext(unittest.TestCase):
    def test_deixis_regex_matches_only_screen_references(self):
        script = (
            f"const re={_deixis_source()};"
            "const out=process.argv.slice(1).map(s=>re.test(s)?'1':'0');"
            "process.stdout.write(out.join(''));"
        )
        cases = {
            "review this post as a cold viewer": "1",
            "what's on my screen?": "1",
            "fix the open carousel": "1",
            "I'm looking at the demo profile": "1",
            "should I commit the assessment as-is?": "0",
            "update intake first": "0",
            "this is the plan for acme": "0",
        }
        res = subprocess.run(["node", "-e", script, *cases],
                             capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout, "".join(cases.values()))

    def test_ongoing_chat_demotes_view_to_background(self):
        self.assertIn("if (history.length <= 1) return true;", APP_JS)
        self.assertIn("## Screen (background only)", APP_JS)
        self.assertIn("viewPrimary ? (CURRENT_PROFILE_SLUG || STATE.profile) : null", APP_JS)
        self.assertIn("if (CURRENT_POST && viewPrimary) {", APP_JS)

    def test_ongoing_unbound_chat_not_bound_by_open_tab(self):
        body = APP_JS[APP_JS.index("function projectForTurn"):]
        body = body[:body.index("async function buildContext")]
        guard = body.index("if (history.length > 1) return null;")
        self.assertLess(body.index("if (activeChatProject)"), guard)
        self.assertLess(guard, body.index("if (STATE.project)"))

    def test_rail_says_topic_is_thread_not_screen(self):
        from dashboard.ai_rules import CHAT_RAIL
        self.assertIn("Topic = thread + @tags", CHAT_RAIL)


if __name__ == "__main__":
    unittest.main()
