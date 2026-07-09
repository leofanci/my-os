import io, json, tempfile, unittest
from pathlib import Path

import index
from tests.test_index_projects import write
import dashboard.server as server

# server.py does a bare `import fileops` / `import db` (sys.path trick), which
# caches under different sys.modules keys than `dashboard.fileops` / `dashboard.db`
# — two distinct module objects. Routes use server's own references, so tests
# must patch those, not the `dashboard.*`-qualified ones.
fileops = server.fileops
db = server.db


def _handler():
    h = server.Handler.__new__(server.Handler)  # bypass __init__/socket
    h.send_response = h.send_header = h.end_headers = lambda *a, **k: None
    return h


def _get(path):
    h = _handler()
    h.path = path
    h.wfile = io.BytesIO()
    h.do_GET()
    return json.loads(h.wfile.getvalue().decode())


def _post(path, body):
    h = _handler()
    payload = json.dumps(body).encode()
    h.path = path
    h.headers = {"Content-Length": str(len(payload))}
    h.rfile = io.BytesIO(payload)
    h.wfile = io.BytesIO()
    h.do_POST()
    return json.loads(h.wfile.getvalue().decode())


class BriefsVoicesRoutesTest(unittest.TestCase):
    def setUp(self):
        self._prev_root = fileops.ROOT
        self._prev_db_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        prof = root / "projects" / "acme" / "profiles" / "demo"
        write(root / "projects" / "acme" / "project.md", "---\nname: Acme\n---")
        write(prof / "profile.md", "---\nname: Demo\n---")
        write(prof / "channels" / "demo-tt" / "channel.md", "---\nplatform: tiktok\n---")
        (prof / "content").mkdir(parents=True, exist_ok=True)
        fileops.ROOT = root
        db.DB_PATH = root / "database" / "data" / "os.db"
        index.build(root)

    def tearDown(self):
        fileops.ROOT = self._prev_root
        db.DB_PATH = self._prev_db_path
        self.tmp.cleanup()

    def test_platforms_route(self):
        out = _get("/api/profile/demo/platforms")
        self.assertEqual(out["platforms"], ["tiktok"])

    def test_brief_specs_list_create_update_delete(self):
        specs = _get("/api/profile/demo/brief-specs")
        self.assertEqual(len(specs["specs"]), 1)
        created = _post("/api/profile/demo/brief-specs", {"text": "tiktok rules", "platforms": "tiktok"})
        self.assertEqual(created["brief_id"], "br2")
        upd = _post("/api/profile/demo/brief-specs/br2/update", {"text": "updated"})
        self.assertTrue(upd["ok"])
        got = _get("/api/profile/demo/brief-specs/br2")
        self.assertEqual(got["text"].strip(), "updated")
        deleted = _post("/api/profile/demo/brief-specs/br2/delete", {})
        self.assertTrue(deleted["deleted"])
        specs_after = _get("/api/profile/demo/brief-specs")
        self.assertEqual(len(specs_after["specs"]), 1)

    def test_voices_list_create_update_delete(self):
        voices = _get("/api/profile/demo/voices")
        self.assertEqual(len(voices["voices"]), 1)
        created = _post("/api/profile/demo/voices", {"text": "faster cuts", "platforms": "tiktok"})
        self.assertEqual(created["voice_id"], "vc2")
        upd = _post("/api/profile/demo/voices/vc2/update", {"text": "updated voice"})
        self.assertTrue(upd["ok"])
        got = _get("/api/profile/demo/voices/vc2")
        self.assertEqual(got["text"].strip(), "updated voice")
        deleted = _post("/api/profile/demo/voices/vc2/delete", {})
        self.assertTrue(deleted["deleted"])

    def test_profile_update_still_works_and_is_not_swallowed_by_new_routes(self):
        out = _post("/api/profile/demo/update", {"name": "Demo Renamed", "topic": "film"})
        self.assertTrue(out["ok"])
        self.assertEqual(fileops.read_profile("demo")["name"], "Demo Renamed")


if __name__ == "__main__":
    unittest.main()
