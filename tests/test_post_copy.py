import json
import subprocess
import threading
import unittest
import urllib.request
from pathlib import Path

from dashboard import server


ROOT = Path(__file__).resolve().parents[1]
POST_COPY_JS = ROOT / "dashboard" / "post-copy.js"
APP_JS = ROOT / "dashboard" / "app.js"
APP_HTML = ROOT / "dashboard" / "app.html"


class TestPostCopy(unittest.TestCase):
    def test_formats_authored_content_without_ids_labels_or_slide_numbers(self):
        brief = {
            "id": "pr1.pf1.sec00.po1",
            "platform": "demo-platform",
            "format": "carousel",
            "objective": "engagement",
            "pillar": "demo-pillar",
            "cover_overlay": "Demo cover",
            "slide_overlays": [
                {"slide": 1, "overlay": "First slide\nFirst detail"},
                {"slide": 2, "overlay": "Second slide\nSecond detail"},
            ],
            "caption": "Demo caption\n#demo",
            "gen_prompts": ["Production prompt"],
            "visual_brief": {"mood": "Production mood"},
            "channels": ["demo-channel"],
        }
        script = (
            "const {formatPostContent}=require(process.argv[1]);"
            "const brief=JSON.parse(process.argv[2]);"
            "process.stdout.write(formatPostContent({}, brief));"
        )

        result = subprocess.run(
            ["node", "-e", script, str(POST_COPY_JS), json.dumps(brief)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.stdout,
            "Demo cover\n\n"
            "First slide\nFirst detail\n\n"
            "Second slide\nSecond detail\n\n"
            "Demo caption\n#demo",
        )
        self.assertNotIn("pr1.pf1.sec00.po1", result.stdout)
        self.assertNotIn("Cover overlay", result.stdout)
        self.assertNotIn("demo-channel", result.stdout)
        self.assertNotIn("demo-platform", result.stdout)
        self.assertNotIn("Production prompt", result.stdout)
        self.assertNotIn("Production mood", result.stdout)

    def test_nested_overlay_object_keeps_authored_sibling_content(self):
        brief = {
            "id": "pr1.pf1.sec00.po1",
            "custom_block": {
                "overlay": "Overlay text",
                "headline": "Headline text",
                "body": "Body text",
            },
        }
        script = (
            "const {formatPostContent}=require(process.argv[1]);"
            "const brief=JSON.parse(process.argv[2]);"
            "process.stdout.write(formatPostContent({}, brief));"
        )

        result = subprocess.run(
            ["node", "-e", script, str(POST_COPY_JS), json.dumps(brief)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout, "Overlay text\n\nHeadline text\n\nBody text")

    def test_post_detail_wires_copy_button_to_clipboard(self):
        source = APP_JS.read_text(encoding="utf-8")
        html = APP_HTML.read_text(encoding="utf-8")

        self.assertIn('<script src="/post-copy.js"></script>', html)
        self.assertIn('id="pd-copy"', source)
        self.assertIn("PostCopy.formatPostContent(slot, brief)", source)
        self.assertIn("copyText(postContent,", source)

    def test_post_copy_script_is_served_and_cache_busted(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            # The app shell needs the per-run session cookie (see do_GET "/").
            shell = urllib.request.Request(base + "/", headers={
                "Cookie": f"{server.AUTH_COOKIE}={server.AUTH_TOKEN}"})
            with urllib.request.urlopen(shell) as response:
                html = response.read().decode("utf-8")
            with urllib.request.urlopen(base + "/post-copy.js") as response:
                script = response.read().decode("utf-8")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertRegex(html, r'/post-copy\.js\?v=\d+"')
        self.assertIn("function formatPostContent", script)

    def test_clipboard_fallback_reports_failure_when_copy_command_fails(self):
        script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("function fallbackCopyText");
const end = source.indexOf("function copyMentionId");
const messages = [];
const textarea = { value: "", style: {}, focus() {}, select() {} };
const context = {
  document: {
    createElement() { return textarea; },
    body: { appendChild() {}, removeChild() {} },
    execCommand() { return false; },
  },
  navigator: {},
  window: { isSecureContext: false },
  toast(message) { messages.push(message); },
};
vm.runInNewContext(source.slice(start, end) + '; copyText("demo", "Copied");', context);
process.stdout.write(JSON.stringify(messages));
'''
        result = subprocess.run(
            ["node", "-e", script, str(APP_JS)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(json.loads(result.stdout), ["Copy failed"])


if __name__ == "__main__":
    unittest.main()
