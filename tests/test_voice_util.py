import tempfile
import unittest
from pathlib import Path

from core.voice_util import (
    delete_voice,
    list_voice_ids,
    next_voice_id,
    read_voice_platforms,
    read_voice_text,
    write_voice_text,
)


class VoiceStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profile"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_default_vc1(self):
        write_voice_text(self.profile_dir, "Warm, direct, no corporate speak.")
        self.assertEqual(read_voice_text(self.profile_dir).strip(), "Warm, direct, no corporate speak.")
        self.assertEqual(read_voice_platforms(self.profile_dir), "all")

    def test_second_voice_with_platform_tag(self):
        write_voice_text(self.profile_dir, "Faster cuts, slang okay.", voice_id="vc2", platforms="tiktok")
        self.assertEqual(read_voice_text(self.profile_dir, "vc2").strip(), "Faster cuts, slang okay.")
        self.assertEqual(read_voice_platforms(self.profile_dir, "vc2"), "tiktok")

    def test_list_and_next_id(self):
        self.assertEqual(list_voice_ids(self.profile_dir), ["vc1"])
        self.assertEqual(next_voice_id(self.profile_dir), "vc2")
        write_voice_text(self.profile_dir, "x", voice_id="vc2")
        self.assertEqual(list_voice_ids(self.profile_dir), ["vc1", "vc2"])
        self.assertEqual(next_voice_id(self.profile_dir), "vc3")

    def test_delete_rejects_last_one(self):
        with self.assertRaises(ValueError):
            delete_voice(self.profile_dir, "vc1")

    def test_delete_rejects_vc1_even_when_others_exist(self):
        write_voice_text(self.profile_dir, "second", voice_id="vc2")
        with self.assertRaises(ValueError):
            delete_voice(self.profile_dir, "vc1")
        self.assertEqual(list_voice_ids(self.profile_dir), ["vc1", "vc2"])

    def test_legacy_profile_body_migrates_on_first_touch(self):
        (self.profile_dir / "profile.md").write_text(
            "---\nname: Demo\ntopic: demo-topic\nproject: acme\n---\nLegacy voice text.\n",
            encoding="utf-8",
        )
        self.assertEqual(read_voice_text(self.profile_dir).strip(), "Legacy voice text.")
        # profile.md frontmatter untouched, body cleared
        text = (self.profile_dir / "profile.md").read_text(encoding="utf-8")
        self.assertIn("name: Demo", text)
        self.assertNotIn("Legacy voice text.", text)


if __name__ == "__main__":
    unittest.main()
