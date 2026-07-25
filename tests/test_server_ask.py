import io, tempfile, unittest
from pathlib import Path
from unittest import mock
import dashboard.server as server


class FakeSession:
    _started = False
    _turn_count = 0
    _skill_explicit = False
    _last_skill = None

    def is_fresh(self):
        return not self._started

    def note_skill(self, skill, explicit=False):
        pass

    def ask(self, text, with_web=False, model=None):
        yield ("delta", "Hi ")
        yield ("delta", "there")
        yield ("done", {"result": "Hi there"})


def _bare_handler(sink):
    """A Handler with the socket-backed I/O stubbed out, writing to `sink`."""
    h = server.Handler.__new__(server.Handler)  # bypass __init__/socket
    h.wfile = sink
    h.send_response = h.send_header = h.end_headers = lambda *a, **k: None
    return h


def _captured(body, tree=None):
    """Run _handle_ask with a session that records the prompt + routing args."""
    seen = {}

    class CaptureSession:
        _started = False
        _turn_count = 0
        _last_skill = None
        _skill_explicit = False

        def is_fresh(self):
            return not self._started

        def note_skill(self, skill, explicit=False):
            pass

        def ask(self, text, with_web=False, model=None):
            seen["text"] = text
            seen["with_web"] = with_web
            seen["model"] = model
            yield ("done", {"result": "ok"})

    h = _bare_handler(io.BytesIO())
    # build_id_registry persists numbering under {server.ROOT}/database/data/ —
    # isolate it so fixture slugs (acme, demo, ...) never leak into the real repo.
    with tempfile.TemporaryDirectory() as tmp, \
         mock.patch.object(server, "get_chat_session", return_value=CaptureSession()), \
         mock.patch.object(server, "ROOT", Path(tmp)), \
         mock.patch.object(server.db, "tree", return_value=tree or []):
        h._handle_ask(body)
    return seen


def _captured_prompt(body, tree=None):
    """Back-compat helper: just the assembled prompt text."""
    return _captured(body, tree)["text"]


class SSE(unittest.TestCase):
    def test_handle_ask_streams_sse(self):
        sink = io.BytesIO()
        h = _bare_handler(sink)
        with mock.patch.object(server, "get_chat_session", return_value=FakeSession()):
            h._handle_ask({"messages": [{"role": "user", "content": "hi"}]})
        out = sink.getvalue().decode()
        self.assertIn('data: {"delta": "Hi "}', out)
        self.assertIn('data: [DONE]', out)
        self.assertLess(out.index('"delta": "Hi "'), out.index("[DONE]"))

    def test_handle_ask_prepends_state_snapshot(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [{"slug": "demo-tiktok", "name": "TikTok",
                                             "platform": "tiktok"}]}]}]
        text = _captured_prompt({"messages": [{"role": "user", "content": "do a thing"}]}, tree)
        self.assertIn("## Current GTM OS state", text)
        self.assertIn("### acme id=pr1 (brand)", text)
        self.assertIn("## Request\ndo a thing", text)

    def test_handle_ask_includes_client_context(self):
        ctx = "Current view: Profiles · Demo\n## Attached files\n### plan.md\n```\nhello\n```"
        text = _captured_prompt({"messages": [{"role": "user", "content": "summarize"}],
                                 "context": ctx})
        # the client-supplied context (current view + attached file contents)
        # must reach the agent, ahead of the request itself
        self.assertIn("### plan.md", text)
        self.assertIn("Current view: Profiles · Demo", text)
        self.assertLess(text.index("### plan.md"), text.index("## Request\nsummarize"))

    def test_handle_ask_without_context_still_works(self):
        text = _captured_prompt({"messages": [{"role": "user", "content": "hi"}]})
        self.assertIn("## Request\nhi", text)


class RouteSkill(unittest.TestCase):
    def test_plain_chat_routes_nothing(self):
        for msg in ["hi", "what posts do I have?", "rename the project to Acme",
                    "thanks!", "mark draft-001 done"]:
            self.assertIsNone(server._route_skill(msg), msg)

    def test_keywords_suggest_not_route(self):
        cases = {
            "is this idea worth doing?": "problem-validation",
            "help me with positioning": "positioning",
            "fill the left panel with this spec": "gtm-os",
        }
        for msg, want in cases.items():
            self.assertIsNone(server._explicit_skill(msg), msg)
            self.assertEqual(server._suggest_skill(msg), want, msg)

    def test_explicit_tag_routes_skill(self):
        self.assertEqual(server._explicit_skill("run @gtm-assessment on acme"), "gtm-assessment")
        self.assertEqual(server._explicit_skill("use /problem-validation here"), "problem-validation")
        self.assertEqual(server._explicit_skill("@gtm-os help"), "gtm-os")

    def test_unknown_mention_does_not_route(self):
        self.assertIsNone(server._route_skill("email @bob about the @stuff"))

    def test_known_skills_have_files(self):
        for name in server.SKILL_NAMES:
            self.assertTrue(server._load_skill_body(name), f"{name} body empty/missing")

    def test_skills_index_has_name_and_description(self):
        idx = server._skills_index()
        self.assertTrue(idx)
        names = {s["name"] for s in idx}
        self.assertIn("problem-validation", names)
        for s in idx:
            self.assertIn("name", s)
            self.assertIn("description", s)

    def test_web_token_forces_web(self):
        self.assertTrue(server._needs_web("write copy /web"))
        self.assertFalse(server._needs_web("write copy"))

    def test_current_view_in_context_does_not_force_web(self):
        """buildContext header must not escalate model via WEB_RE `current`."""
        ctx = "Current view: Profiles · Demo\nSection: Demo Brand"
        self.assertFalse(server._needs_web(ctx))
        seen = _captured({"messages": [{"role": "user", "content": "hi"}],
                          "context": ctx})
        self.assertFalse(seen["with_web"])
        self.assertEqual(seen["model"], server.chat_session.CHAT_MODEL)


class NeedsWebAndModel(unittest.TestCase):
    def test_web_requires_explicit_tag(self):
        self.assertFalse(server._needs_web("search the web for X"))
        self.assertFalse(server._needs_web("what's the latest on this"))
        self.assertTrue(server._needs_web("look this up /web"))
        self.assertFalse(server._needs_web("rename the project"))

    def test_research_skill_forces_web(self):
        self.assertTrue(server._needs_web("anything", skill="competitor-scan"))
        self.assertFalse(server._needs_web("anything", skill="positioning"))

    def test_model_tiering(self):
        self.assertEqual(server._pick_model(None, False), server.chat_session.CHAT_MODEL)
        self.assertEqual(
            server._pick_model("positioning", False, "help with positioning", explicit=True),
            server.chat_session.ESCALATED_MODEL,
        )
        self.assertEqual(
            server._pick_model("positioning", False, "help with positioning", explicit=False),
            server.chat_session.CHAT_MODEL,
        )
        self.assertEqual(server._pick_model(None, True), server.chat_session.ESCALATED_MODEL)

    def test_read_only_tagged_skill_stays_haiku(self):
        self.assertEqual(
            server._pick_model("positioning", False, "what positioning memos do we have?",
                               explicit=True),
            server.chat_session.CHAT_MODEL,
        )

    def test_continuation_escalates(self):
        sess = type("S", (), {"_skill_explicit": True, "_last_skill": "gtm-os"})()
        self.assertEqual(
            server._pick_model(None, False, "yes save sec02", sess),
            server.chat_session.ESCALATED_MODEL,
        )

    def test_active_thread_clarifying_answer_stays_escalated(self):
        """A natural clarifying-answer reply mid-skill (not "yes"/"save"/etc)
        must not silently drop to Haiku — that caused a Sonnet→Haiku→Sonnet
        ping-pong that pays the uncached system-prompt cost twice."""
        sess = type("S", (), {"_skill_explicit": True, "_last_skill": "market-sizing"})()
        self.assertEqual(
            server._pick_model(None, False, "the segment is small business owners in Italy", sess),
            server.chat_session.ESCALATED_MODEL,
        )

    def test_active_thread_standalone_read_still_cheap(self):
        """A genuine unrelated read-only query mid-thread still falls back to
        the cheap model — only reads should, not every non-magic-word reply."""
        sess = type("S", (), {"_skill_explicit": True, "_last_skill": "market-sizing"})()
        self.assertEqual(
            server._pick_model(None, False, "what posts do I have", sess),
            server.chat_session.CHAT_MODEL,
        )


class SkillRouting(unittest.TestCase):
    def test_cheap_turn_no_skill_no_web_cheap_model(self):
        seen = _captured({"messages": [{"role": "user", "content": "what posts do I have?"}]})
        self.assertFalse(seen["with_web"])
        self.assertEqual(seen["model"], server.chat_session.CHAT_MODEL)
        self.assertNotIn("## Active skill:", seen["text"])

    def test_tagged_turn_injects_skill_and_escalates(self):
        seen = _captured({"messages": [{"role": "user", "content": "/problem-validation validate this idea"}]})
        self.assertIn("## Active skill: problem-validation", seen["text"])
        self.assertEqual(seen["model"], server.chat_session.ESCALATED_MODEL)

    def test_untagged_read_gets_hint_not_skill(self):
        seen = _captured({"messages": [{"role": "user", "content": "help me with positioning"}]})
        self.assertIn("Skill hint", seen["text"])
        self.assertNotIn("## Active skill:", seen["text"])
        self.assertEqual(seen["model"], server.chat_session.CHAT_MODEL)

    def test_untagged_write_blocked_at_gate(self):
        sink = io.BytesIO()
        h = _bare_handler(sink)

        class S:
            _started = True
            _turn_count = 1
            _last_skill = None
            _skill_explicit = False

            def is_fresh(self):
                return False

            def note_skill(self, skill, explicit=False):
                pass

        with mock.patch.object(server, "get_chat_session", return_value=S()):
            h._handle_ask({"messages": [{"role": "user", "content": "fill all the tabs"}]})
        out = sink.getvalue().decode()
        self.assertIn("Tag /gtm-os", out)
        self.assertIn("[DONE]", out)
        self.assertNotIn("Active skill", out)


class ComposeTurnPrompt(unittest.TestCase):
    def setUp(self):
        # compose_turn_prompt -> state_snapshot persists numbering under
        # {server.ROOT}/database/data/ — isolate so fixture slugs (acme)
        # never leak into the real repo's registry file.
        self.tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(server, "ROOT", Path(self.tmp.name))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def _sess(self, *, started=False, turn_count=0, last_skill=None):
        class S:
            pass
        s = S()
        s._started = started
        s._turn_count = turn_count
        s._last_skill = last_skill
        s.is_fresh = lambda: not s._started
        return s

    def test_fresh_includes_snapshot(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project", "profiles": []}]
        text = server.compose_turn_prompt(
            user_msg="hi", context="", skill=None,
            session=self._sess(), projects=tree,
        )
        self.assertIn("## Current GTM OS state", text)
        self.assertNotIn("resumed session", text)

    def test_resume_continuation_keeps_skill_stub(self):
        s = self._sess(started=True, turn_count=2, last_skill="gtm-os")
        s._skill_explicit = True
        tree = [{"slug": "acme", "kind": "brand", "type": "project", "profiles": []}]
        text = server.compose_turn_prompt(
            user_msg="yes save it", context="", skill=None,
            session=s, projects=tree,
        )
        self.assertNotIn("## Current GTM OS state", text)
        self.assertIn("resumed session", text)
        self.assertIn("continuing", text)
        self.assertNotIn("Tab map + write gate", text)

    def test_resume_new_explicit_tag_gets_full_body(self):
        text = server.compose_turn_prompt(
            user_msg="now pricing", context="", skill="pricing-strategy",
            session=self._sess(started=True, turn_count=1, last_skill="positioning"),
            projects=[], explicit=True,
        )
        self.assertIn("## Active skill: pricing-strategy", text)
        self.assertNotIn("continuing", text)


class StateSnapshot(unittest.TestCase):
    def setUp(self):
        # build_id_registry now persists numbering to {root}/database/data/
        # id_registry.json — isolate ROOT so fixture slugs (acme, solo, p2)
        # never leak into the real repo's registry file.
        self.tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(server, "ROOT", Path(self.tmp.name))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def test_empty_tree(self):
        out = server.state_snapshot([])
        self.assertTrue(out.startswith("## Current GTM OS state"))
        self.assertIn("(no projects yet)", out)

    def test_nested_outline(self):
        tree = [{"slug": "acme", "kind": "brand", "type": "project",
                 "profiles": [{"slug": "demo", "name": "Demo Brand",
                               "channels": [
                                   {"slug": "demo-tiktok", "name": "TikTok", "platform": "tiktok"},
                                   {"slug": "demo-ig", "name": "Instagram", "platform": "instagram"},
                               ]}]}]
        out = server.state_snapshot(tree)
        self.assertIn("id=pr1", out)
        self.assertIn("id=pr1.sec02", out)
        self.assertIn("id=pr1.pf1", out)
        self.assertIn("id=pr1.pf1.ch1", out)
        self.assertIn("id=pr1.pf1.ch2", out)

    def test_project_no_profiles_and_profile_no_channels(self):
        tree = [{"slug": "solo", "type": "project", "profiles": []},
                {"slug": "p2", "kind": "venture", "type": "project",
                 "profiles": [{"slug": "prof", "name": "Prof", "channels": []}]}]
        out = server.state_snapshot(tree)
        self.assertIn("id=pr1", out)
        self.assertIn("id=pr2.pf1", out)
        self.assertNotIn("channel", out)


if __name__ == "__main__":
    unittest.main()
