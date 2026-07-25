import io, json, subprocess, tempfile, unittest, contextlib
from pathlib import Path

import dashboard.fileops as fileops
import dashboard.osctl as osctl


def run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = osctl.main(argv)
    line = buf.getvalue().strip().splitlines()[-1]
    return code, json.loads(line)


MOCK_ENGINE_JSON = json.dumps({
    "query": "demo topic",
    "generated_at": "2026-07-20T00:00:00Z",
    "clusters": [
        {"title": "Low signal", "summary": "quiet", "sources": ["github"], "engagement_total": 3},
        {"title": "High signal", "summary": "people are talking", "sources": ["reddit"], "engagement_total": 120},
        {"title": "Mid signal", "summary": "some chatter", "sources": ["hackernews"], "engagement_total": 40},
    ],
})


class ResearchSignalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name) / "last30days.py"
        self.script.write_text("# stub\n", encoding="utf-8")
        self._orig_script_path = fileops.LAST30DAYS_SCRIPT
        fileops.LAST30DAYS_SCRIPT = self.script
        self._orig_run = subprocess.run

    def tearDown(self):
        fileops.LAST30DAYS_SCRIPT = self._orig_script_path
        subprocess.run = self._orig_run
        self.tmp.cleanup()

    def _mock_success(self, stdout=MOCK_ENGINE_JSON, returncode=0, stderr=""):
        class R:
            pass
        r = R()
        r.returncode = returncode
        r.stdout = stdout
        r.stderr = stderr

        def mock_run(cmd, **kw):
            return r
        subprocess.run = mock_run

    def test_returns_clusters_sorted_by_engagement_descending(self):
        self._mock_success()
        result = fileops.research_signal("demo topic")
        titles = [c["title"] for c in result["clusters"]]
        self.assertEqual(titles, ["High signal", "Mid signal", "Low signal"])
        self.assertEqual(result["query"], "demo topic")
        self.assertEqual(result["generated_at"], "2026-07-20T00:00:00Z")

    def test_respects_max_clusters(self):
        self._mock_success()
        result = fileops.research_signal("demo topic", max_clusters=2)
        self.assertEqual(len(result["clusters"]), 2)

    def test_raises_on_nonzero_exit(self):
        self._mock_success(returncode=1, stdout="", stderr="boom")
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.research_signal("demo topic")
        self.assertIn("boom", str(ctx.exception))

    def test_raises_on_invalid_json(self):
        self._mock_success(stdout="not json")
        with self.assertRaises(fileops.ActionError):
            fileops.research_signal("demo topic")

    def test_raises_on_timeout(self):
        def mock_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=90)
        subprocess.run = mock_run
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.research_signal("demo topic")
        self.assertIn("timed out", str(ctx.exception))

    def test_raises_when_script_missing(self):
        fileops.LAST30DAYS_SCRIPT = Path(self.tmp.name) / "missing.py"
        with self.assertRaises(fileops.ActionError) as ctx:
            fileops.research_signal("demo topic")
        self.assertIn("not installed", str(ctx.exception))

    def test_requires_query(self):
        with self.assertRaises(fileops.ActionError):
            fileops.research_signal("   ")

    def test_osctl_research_signal_command(self):
        self._mock_success()
        code, out = run_cli(["research-signal", "--query", "demo topic"])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["clusters"][0]["title"], "High signal")


if __name__ == "__main__":
    unittest.main()
