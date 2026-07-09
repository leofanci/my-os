import tempfile
import unittest
from pathlib import Path

from core.brief_spec_util import (
    _carousel_slide_bounds,
    allowed_brief_keys,
    delete_brief,
    format_for_brief_prompt,
    list_brief_ids,
    merge_fields_from_slot,
    next_brief_id,
    parse_spec_fields,
    read_spec_platforms,
    read_spec_text,
    slot_format,
    validate_brief_obj,
    write_spec_text,
)


class ParseSpecFieldsTest(unittest.TestCase):
    def test_json_keys_and_bullets(self):
        spec = """
        Required output:
        - cover_overlay
        - catchy_title
        {"slides": [], "caption": "ready-to-post body"}
        """
        self.assertEqual(
            set(parse_spec_fields(spec)),
            {"cover_overlay", "catchy_title", "slides", "caption"},
        )

    def test_empty_spec(self):
        self.assertEqual(parse_spec_fields(""), [])

    def test_comma_list_declared_keys(self):
        spec = (
            "Post brief output: a JSON object with exactly these keys, nothing else: "
            "id, title, overlay, slide_overlays, catchy_title, caption, gen_prompts.\n"
            "- death (explicit or implied)\n"
        )
        self.assertEqual(
            parse_spec_fields(spec),
            ["title", "overlay", "slide_overlays", "catchy_title", "caption", "gen_prompts"],
        )
        allowed = allowed_brief_keys(spec)
        self.assertEqual(
            allowed,
            {"id", "channels", "title", "overlay", "slide_overlays",
             "catchy_title", "caption", "gen_prompts"},
        )


class SpecFileRoundtripTest(unittest.TestCase):
    def test_read_write_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof = Path(tmp) / "profiles" / "demo"
            write_spec_text(prof, "Captions under 100 words.")
            self.assertEqual(read_spec_text(prof).strip(), "Captions under 100 words.")

    def test_format_for_brief_prompt(self):
        self.assertIn("PROFILE BRIEF SPEC", format_for_brief_prompt("rule one"))


class MergeFieldsFromSlotTest(unittest.TestCase):
    MOVIE_TALK_SPEC = """
    {
      "id": "post-001",
      "cover_overlay": "...",
      "slide_overlays": [],
      "catchy_title": "...",
      "caption": "..."
    }
    NO other keys: platform, format, objective, pillar.
    """

    def test_empty_spec_keeps_legacy_slot_fill(self):
        self.assertEqual(
            merge_fields_from_slot(""),
            ("channels", "platform", "format", "objective", "pillar"),
        )

    def test_spec_without_identity_keys_only_channels(self):
        self.assertEqual(merge_fields_from_slot(self.MOVIE_TALK_SPEC), ("channels",))

    def test_allowed_keys_follow_spec_template(self):
        allowed = allowed_brief_keys(self.MOVIE_TALK_SPEC)
        self.assertEqual(
            allowed,
            {"id", "channels", "cover_overlay", "slide_overlays", "catchy_title", "caption"},
        )

    def test_curly_quotes_in_spec_still_parse_slide_overlays(self):
        spec = '{\n  \u201cslide_overlays\u201d: []\n  "cover_overlay": "x"\n}'
        self.assertIn("slide_overlays", parse_spec_fields(spec))


class ValidateBriefObjTest(unittest.TestCase):
    def _brief(self, **extra):
        base = {
            "id": "post-001",
            "channels": ["demo-tiktok"],
            "platform": "tiktok",
            "format": "carousel",
            "objective": "engage",
            "pillar": "curiosity",
        }
        base.update(extra)
        return base

    def test_slot_identity_fields_not_required_on_brief(self):
        """platform/format/objective/pillar live on the slot; brief-spec governs brief keys."""
        slot = {"platform": "tiktok", "format": "carousel", "objective": "x", "pillar": "p"}
        errs = validate_brief_obj({"channels": ["x"]}, "post-001", "", slot)
        self.assertFalse(any(k in e for e in errs for k in ("platform", "format", "objective", "pillar")))

    def test_spec_fields_required_when_declared(self):
        spec = '- cover_overlay\n- caption'
        errs = validate_brief_obj(self._brief(), "post-001", spec)
        self.assertIn("missing spec field 'cover_overlay'", errs)
        self.assertIn("missing spec field 'caption'", errs)

    def test_passes_when_spec_fields_present(self):
        spec = '- cover_overlay\n- caption'
        b = self._brief(cover_overlay="hook line", caption="body text")
        self.assertEqual(validate_brief_obj(b, "post-001", spec), [])

    def test_no_channels_spec_skips_channels_validation(self):
        spec = 'NO channels\n{"id": "x", "title": "t", "caption": "c"}'
        b = {"id": "post-001", "title": "t", "caption": "c"}
        self.assertEqual(validate_brief_obj(b, "post-001", spec), [])

    def test_gen_prompts_count_follows_slot_format(self):
        spec = """NO channels
{
  "id": "x",
  "title": "...",
  "overlay": "...",
  "catchy_title": "...",
  "caption": "...",
  "gen_prompts": []
}
— catchy_title: carousel only"""
        base = {
            "id": "post-001", "title": "t", "overlay": "o",
            "caption": "story text here", "gen_prompts": ["p"] * 8,
        }
        self.assertEqual(validate_brief_obj({**base, "catchy_title": "c"}, "post-001", spec), [])
        errs = validate_brief_obj({**base, "catchy_title": "c", "gen_prompts": ["p"]}, "post-001", spec)
        self.assertIn("8-10 gen_prompts", errs[0])
        slot = {"format": "reel"}
        b = {**base, "gen_prompts": ["one video prompt"]}
        self.assertEqual(validate_brief_obj(b, "post-001", spec, slot), [])

    def test_slot_format_defaults_carousel(self):
        self.assertEqual(slot_format({}), "carousel")
        self.assertEqual(slot_format({"format": "reel"}), "reel")

    def test_catchy_title_optional_on_video_slot(self):
        spec = """NO channels
{
  "id": "x",
  "title": "...",
  "overlay": "...",
  "catchy_title": "...",
  "caption": "...",
  "gen_prompts": []
}
— catchy_title: carousel only — omit for video/reel slots."""
        b = {"id": "post-001", "title": "t", "overlay": "o", "caption": "full story text", "gen_prompts": ["p"]}
        slot = {"format": "reel"}
        self.assertEqual(validate_brief_obj(b, "post-001", spec, slot), [])

    def test_slide_overlays_required_on_carousel(self):
        spec = """NO channels
{
  "id": "x",
  "title": "...",
  "overlay": "...",
  "slide_overlays": [{"slide": 1, "overlay": "..."}],
  "catchy_title": "...",
  "caption": "...",
  "gen_prompts": []
}
— overlay: video/reel only — omit for carousel.
— slide_overlays: carousel only — omit for video/reel slots.
— catchy_title: carousel only — omit for video/reel slots."""
        slides = [{"slide": i, "overlay": f"line {i}"} for i in range(1, 9)]
        base = {
            "id": "post-001", "title": "t", "caption": "story",
            "catchy_title": "c", "gen_prompts": ["p"] * 8, "slide_overlays": slides,
        }
        self.assertEqual(validate_brief_obj(base, "post-001", spec), [])
        errs = validate_brief_obj({**base, "slide_overlays": slides[:3]}, "post-001", spec)
        self.assertIn("8-10 slide_overlays", errs[0])
        slot = {"format": "reel"}
        b = {"id": "post-001", "title": "t", "overlay": "o", "caption": "story", "gen_prompts": ["p"]}
        self.assertEqual(validate_brief_obj(b, "post-001", spec, slot), [])

    def test_carousel_max_slides_from_spec(self):
        spec = "carousel only — max 5 slides.\n— gen_prompts: max 5 items"
        self.assertEqual(_carousel_slide_bounds(spec), (1, 5))
        self.assertEqual(_carousel_slide_bounds(""), (8, 10))

    def test_max_five_carousel_brief(self):
        spec = """NO channels
{
  "slide_overlays": [{"slide": 1, "overlay": "..."}],
  "caption": "...",
  "gen_prompts": []
}
— slide_overlays: carousel only — max 5 slides.
— catchy_title: carousel only — omit for video/reel slots."""
        slides = [{"slide": i, "overlay": f"scene {i}"} for i in range(1, 6)]
        b = {
            "id": "post-001", "title": "t", "caption": "story",
            "catchy_title": "c", "gen_prompts": ["p"] * 5, "slide_overlays": slides,
        }
        self.assertEqual(validate_brief_obj(b, "post-001", spec), [])
        errs = validate_brief_obj({**b, "gen_prompts": ["p"] * 6, "slide_overlays": slides + [{"slide": 6, "overlay": "x"}]}, "post-001", spec)
        self.assertTrue(any("1-5" in e for e in errs))

    def test_slide_overlays_must_match_gen_prompts_count(self):
        spec = """NO channels
{
  "slide_overlays": [{"slide": 1, "overlay": "..."}],
  "caption": "...",
  "gen_prompts": []
}
— slide_overlays: carousel only — omit for video/reel slots."""
        slides = [{"slide": i, "overlay": f"line {i}"} for i in range(1, 9)]
        b = {
            "id": "post-001", "caption": "story", "slide_overlays": slides,
            "gen_prompts": ["p"] * 7,
        }
        errs = validate_brief_obj(b, "post-001", spec)
        self.assertIn("must match gen_prompts count", errs[0])


class BriefSpecStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name) / "profile"
        self.profile_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_default_br1(self):
        write_spec_text(self.profile_dir, "Captions under 100 words.")
        self.assertEqual(read_spec_text(self.profile_dir).strip(), "Captions under 100 words.")
        self.assertEqual(read_spec_platforms(self.profile_dir), "all")
        self.assertTrue((self.profile_dir / "brief-specs" / "br1.md").is_file())

    def test_write_and_read_second_brief_with_platforms(self):
        write_spec_text(self.profile_dir, "TikTok: under 40 words.", brief_id="br2", platforms="tiktok")
        self.assertEqual(read_spec_text(self.profile_dir, "br2").strip(), "TikTok: under 40 words.")
        self.assertEqual(read_spec_platforms(self.profile_dir, "br2"), "tiktok")
        # br1 unaffected
        self.assertEqual(read_spec_text(self.profile_dir, "br1").strip(), "")

    def test_update_without_platforms_preserves_existing_tag(self):
        write_spec_text(self.profile_dir, "v1", brief_id="br1", platforms="instagram")
        write_spec_text(self.profile_dir, "v2", brief_id="br1")  # no platforms arg
        self.assertEqual(read_spec_platforms(self.profile_dir, "br1"), "instagram")
        self.assertEqual(read_spec_text(self.profile_dir, "br1").strip(), "v2")

    def test_list_brief_ids_always_includes_br1(self):
        self.assertEqual(list_brief_ids(self.profile_dir), ["br1"])
        write_spec_text(self.profile_dir, "x", brief_id="br3")
        self.assertEqual(list_brief_ids(self.profile_dir), ["br1", "br3"])

    def test_next_brief_id_skips_occupied_and_never_reuses(self):
        self.assertEqual(next_brief_id(self.profile_dir), "br2")  # br1 implicit, so next is br2
        write_spec_text(self.profile_dir, "x", brief_id="br2")
        self.assertEqual(next_brief_id(self.profile_dir), "br3")
        delete_brief(self.profile_dir, "br2")
        self.assertEqual(next_brief_id(self.profile_dir), "br3")  # br2 never reused

    def test_delete_brief_rejects_last_one(self):
        with self.assertRaises(ValueError):
            delete_brief(self.profile_dir, "br1")

    def test_delete_brief_rejects_br1_even_when_others_exist(self):
        # br1 is the permanent default slot — list_brief_ids() always reports
        # it, so "deleting" it while br2 exists would silently reappear.
        write_spec_text(self.profile_dir, "second", brief_id="br2")
        with self.assertRaises(ValueError):
            delete_brief(self.profile_dir, "br1")
        self.assertEqual(list_brief_ids(self.profile_dir), ["br1", "br2"])

    def test_legacy_brief_spec_md_migrates_on_first_touch(self):
        (self.profile_dir / "brief-spec.md").write_text("Legacy rules.", encoding="utf-8")
        self.assertEqual(read_spec_text(self.profile_dir).strip(), "Legacy rules.")
        self.assertEqual(read_spec_platforms(self.profile_dir), "all")
        self.assertFalse((self.profile_dir / "brief-spec.md").exists())
        self.assertTrue((self.profile_dir / "brief-specs" / "br1.md").is_file())


if __name__ == "__main__":
    unittest.main()