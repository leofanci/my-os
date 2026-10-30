"""Connected apps UI: pure helpers (run in node) and the guards around app action cards."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    m = re.search(rf"^(?:async )?function {name}\(.*?\n}}\n", APP_JS, re.S | re.M)
    assert m, f"{name} missing from app.js"
    return m.group(0)


def _run(names, expr):
    script = "\n".join(_fn(n) for n in names) + f"\nprocess.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class Helpers(unittest.TestCase):
    def test_is_app_action(self):
        self.assertEqual(_run(["isAppAction"],
                              '[isAppAction({kind:"app_action"}), isAppAction({summary:"x"}), isAppAction(null)]'),
                         [True, False, False])

    def test_grant_label(self):
        self.assertEqual(_run(["grantLabel"], '[grantLabel(undefined), grantLabel("read"), grantLabel("write")]'),
                         ["Off", "Read", "Read + write"])

    def test_app_status_label(self):
        self.assertEqual(_run(["appStatusLabel"],
                              '[appStatusLabel({auth:"managed"}, true), appStatusLabel({auth:"managed"}, false),'
                              ' appStatusLabel({auth:"own_app"}, false), appStatusLabel({auth:"api_key"}, false)]'),
                         ["Connected", "Connect", "Needs setup", "Connect"])


class Guards(unittest.TestCase):
    def test_send_cleanup_skips_app_actions(self):
        # Any reply answers a chat approval bar; an app action card stays until clicked.
        self.assertIn('stream.querySelectorAll(".approval-bar:not(.app-card)").forEach(el => el.remove());', APP_JS)
        self.assertNotIn('stream.querySelectorAll(".approval-bar").forEach(el => el.remove());', APP_JS)

    def test_dismiss_skips_app_actions(self):
        body = _fn("renderApprovals")
        self.assertIn("isAppAction", body)
        self.assertIn("/api/approvals/dismiss", body)
        card = _fn("wireAppCard")
        self.assertIn('answer("reject")', card)
        self.assertIn("/api/approvals/${encodeURIComponent(a.id)}/${verb}", card)

    def test_integrations_route_and_rail(self):
        self.assertIn("/^\\/integrations$/", APP_JS)
        self.assertIn('data-view="integrations"', APP_JS)


if __name__ == "__main__":
    unittest.main()
