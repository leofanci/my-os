import io
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import generate
from dashboard import fileops, server, ws
from core.numbered_profile_artifact import NumberedArtifactStore


class FilesystemBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.previous_root = fileops.ROOT
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "projects" / "acme").mkdir(parents=True)
        (self.root / "projects" / "acme" / "project.md").write_text(
            "---\nname: Acme\n---\n", encoding="utf-8"
        )
        fileops.ROOT = self.root

    def tearDown(self):
        fileops.ROOT = self.previous_root
        self.temp.cleanup()

    def test_project_delete_rejects_parent_traversal(self):
        victim = self.root / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("keep", encoding="utf-8")

        with self.assertRaises(fileops.ActionError):
            fileops.delete_project("../victim")

        self.assertEqual((victim / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_nested_slug_rejects_path_traversal(self):
        with self.assertRaises(fileops.ActionError):
            fileops.create_profile("acme", "../../victim", {})

    def test_authored_json_cannot_escape_workspace(self):
        outside = self.root.parent / "outside-authored.json"
        outside.write_text('{"private": true}', encoding="utf-8")
        try:
            self.assertIsNone(fileops.read_authored_json("../outside-authored.json"))
        finally:
            outside.unlink()

    def test_numbered_artifact_rejects_unsafe_id(self):
        store = NumberedArtifactStore("brief-specs", "br")
        with self.assertRaises(ValueError):
            store.file(self.root, "../../outside")

    def test_generation_lookup_rejects_glob_and_parent_segments(self):
        with self.assertRaises(generate.JobError):
            generate.find_profile_dir(self.root, "../victim")
        with self.assertRaises(generate.JobError):
            generate.find_channel_dir(self.root, "*")


class WebSocketBoundaryTest(unittest.TestCase):
    def test_unmasked_client_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            ws.decode_frame(b"\x81\x02hi", require_masked=True)

    def test_declared_oversized_frame_is_rejected_before_body_arrives(self):
        header = bytes([0x82, 0xFF]) + struct.pack("!Q", 1025)
        with self.assertRaises(ValueError):
            ws.decode_frame(header, max_payload=1024, require_masked=True)


class HttpBoundaryTest(unittest.TestCase):
    def handler(self, headers):
        h = server.Handler.__new__(server.Handler)
        h.client_address = ("127.0.0.1", 12345)
        h.server = SimpleNamespace(server_address=("127.0.0.1", 8765))
        h.headers = headers
        return h

    def test_api_auth_requires_process_cookie(self):
        h = self.handler({"Host": "127.0.0.1:8765"})
        self.assertFalse(h._authorized())
        h.headers["Cookie"] = f"{server.AUTH_COOKIE}={server.AUTH_TOKEN}"
        self.assertTrue(h._authorized())

    def test_host_and_websocket_origin_are_exact(self):
        cookie = f"{server.AUTH_COOKIE}={server.AUTH_TOKEN}"
        h = self.handler({
            "Host": "attacker.example",
            "Cookie": cookie,
            "Origin": "http://attacker.example",
        })
        self.assertFalse(h._authorized(require_origin=True))

        h.headers = {
            "Host": "127.0.0.1:8765",
            "Cookie": cookie,
            "Origin": "http://127.0.0.1:8765",
        }
        self.assertTrue(h._authorized(require_origin=True))

    def test_json_body_limit_is_enforced_before_read(self):
        h = self.handler({"Content-Length": str(server.MAX_JSON_BYTES + 1)})
        h.rfile = io.BytesIO(b"")
        with self.assertRaises(ValueError):
            h._read_json()


class BrowserOutputBoundaryTest(unittest.TestCase):
    def test_html_escape_covers_quoted_attributes(self):
        source = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("/[&<>\"']/g", source)
        self.assertIn("&quot;", source)
        self.assertIn("&#39;", source)


if __name__ == "__main__":
    unittest.main()
