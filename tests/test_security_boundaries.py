import hmac
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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


class LoginAndLocalFilesTest(unittest.TestCase):
    """GET / hands out the session cookie only to someone who knows the token."""

    def get(self, path, cookie=""):
        h = server.Handler.__new__(server.Handler)
        h.client_address = ("127.0.0.1", 12345)
        h.server = SimpleNamespace(server_address=("127.0.0.1", 8765))
        h.headers = {"Host": "127.0.0.1:8765", "Cookie": cookie}
        h.path = path
        h.wfile = io.BytesIO()
        sent = {"headers": {}}
        h.send_response = lambda code, *a: sent.__setitem__("code", code)
        h.send_header = lambda k, v: sent["headers"].__setitem__(k, v)
        h.end_headers = lambda: None
        h.do_GET()
        sent["body"] = h.wfile.getvalue()
        return sent

    def test_root_without_token_or_cookie_gets_no_cookie(self):
        sent = self.get("/")
        self.assertEqual(sent["code"], 403)
        self.assertNotIn("Set-Cookie", sent["headers"])
        self.assertEqual(self.get("/?token=wrong")["code"], 403)
        self.assertEqual(self.get("/?token=%C3%A9")["code"], 403)  # non-ASCII: no crash

    def test_token_is_exchanged_for_cookie_then_cookie_serves_app(self):
        sent = self.get(f"/?token={server.AUTH_TOKEN}")
        self.assertEqual(sent["code"], 302)
        self.assertEqual(sent["headers"]["Location"], "/")
        self.assertIn(server.AUTH_TOKEN, sent["headers"]["Set-Cookie"])
        cookie = f"{server.AUTH_COOKIE}={server.AUTH_TOKEN}"
        self.assertEqual(self.get("/", cookie)["code"], 200)

    def test_healthz_is_public_but_reveals_nothing(self):
        sent = self.get("/healthz")
        self.assertEqual(sent["code"], 200)
        self.assertNotIn("Set-Cookie", sent["headers"])

    def test_healthz_nonce_proves_token_without_revealing_it(self):
        h_out = self.get("/healthz?nonce=abc123")
        self.assertEqual(h_out["code"], 200)
        body = json.loads(h_out["body"])
        want = hmac.new(server.AUTH_TOKEN.encode(), b"abc123", "sha256").hexdigest()
        self.assertEqual(body, {"app": "myOS", "proof": want})
        self.assertNotIn(server.AUTH_TOKEN.encode(), h_out["body"])

    def test_request_log_redacts_login_token(self):
        h = server.Handler.__new__(server.Handler)
        err = io.StringIO()
        with mock.patch.object(server.sys, "stderr", err):
            h.log_message('"%s" %s %s', f"GET /?token={server.AUTH_TOKEN} HTTP/1.1", "302", "-")
            h.log_message('"%s" %s %s', f"GET /x?a=1&token={server.AUTH_TOKEN}&b=2 HTTP/1.1", "200", "-")
        self.assertNotIn(server.AUTH_TOKEN, err.getvalue())
        self.assertIn("/?token=<redacted> HTTP/1.1", err.getvalue())
        self.assertIn("&token=<redacted>&b=2", err.getvalue())

    def test_osctl_read_file_refuses_token_file(self):
        from dashboard import osctl
        with tempfile.TemporaryDirectory() as d, mock.patch.object(fileops, "ROOT", Path(d)):
            (Path(d) / "dashboard").mkdir()
            (Path(d) / "dashboard" / ".auth-token").write_text("secret", encoding="utf-8")
            out = io.StringIO()
            with mock.patch("sys.stdout", out):
                osctl.main(["read-file", "--path", "dashboard/.auth-token"])
        self.assertIn("secret files are not readable", out.getvalue())
        self.assertNotIn('"content"', out.getvalue())

    def test_token_file_is_owner_only_and_removed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".auth-token"
            server.write_token_file(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), server.AUTH_TOKEN)
            server.remove_token_file(path)
            self.assertFalse(path.exists())

    def test_uploads_live_in_private_dir_removed_on_shutdown(self):
        d = Path(server.upload_dir())
        self.assertEqual(d.stat().st_mode & 0o777, 0o700)
        server.remove_uploads()
        self.assertFalse(d.exists())


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
