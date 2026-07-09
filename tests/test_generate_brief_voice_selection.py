import tempfile, unittest
from pathlib import Path

from generate import build_voice_cascade
from core.voice_util import write_voice_text


class VoiceCascadeSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profiles" / "demo"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_voice_id_used_when_unspecified(self):
        write_voice_text(self.profile_dir, "Default voice text.")
        cascade = build_voice_cascade(self.profile_dir)
        self.assertIn("Default voice text.", cascade)

    def test_explicit_voice_id_selects_that_voice(self):
        write_voice_text(self.profile_dir, "Default voice text.")
        write_voice_text(self.profile_dir, "TikTok voice text.", voice_id="vc2")
        cascade = build_voice_cascade(self.profile_dir, voice_id="vc2")
        self.assertIn("TikTok voice text.", cascade)
        self.assertNotIn("Default voice text.", cascade)


if __name__ == "__main__":
    unittest.main()
