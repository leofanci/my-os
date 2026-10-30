"""Approval cards for app actions are built from the real arguments, in full."""
import unittest

from core import app_preview


class Preview(unittest.TestCase):
    def test_gmail_send_shows_everything(self):
        body = "x" * 5000
        p = app_preview.build("GMAIL_SEND_EMAIL", {
            "recipient_email": "a@example.com", "cc": ["b@example.com"], "subject": "Hi", "body": body})
        self.assertEqual(p["title"], "Send email")
        fields = dict(p["fields"])
        self.assertEqual(fields["To"], "a@example.com")
        self.assertEqual(fields["Cc"], "b@example.com")
        self.assertEqual(fields["Subject"], "Hi")
        self.assertEqual(fields["Body"], body)

    def test_calendar_event_fields(self):
        p = app_preview.build("GOOGLECALENDAR_CREATE_EVENT", {
            "summary": "Sync", "start_datetime": "2026-11-02T10:00", "attendees": ["a@example.com"]})
        fields = dict(p["fields"])
        self.assertEqual(p["title"], "Create calendar event")
        self.assertEqual(fields["Title"], "Sync")
        self.assertEqual(fields["Start"], "2026-11-02T10:00")
        self.assertEqual(fields["Attendees"], "a@example.com")

    def test_generic_title_and_fields(self):
        p = app_preview.build("INSTAGRAM_CREATE_CAROUSEL_CONTAINER", {
            "caption": "c" * 3000, "children": ["1", "2"], "nested": {"k": 1}}, toolkit="instagram")
        self.assertEqual(p["title"], "Instagram: create carousel container")
        fields = dict(p["fields"])
        self.assertEqual(fields["caption"], "c" * 3000)
        self.assertIn('"1"', fields["children"])
        self.assertIn('"k": 1', fields["nested"])

    def test_generic_multiword_toolkit(self):
        p = app_preview.build("GOOGLE_MAPS_CREATE_TILES_SESSION", {}, toolkit="google_maps")
        self.assertEqual(p["title"], "Google maps: create tiles session")

    def test_tailored_keeps_unknown_args(self):
        p = app_preview.build("GMAIL_SEND_EMAIL", {"recipient_email": "a@example.com", "is_html": True})
        self.assertIn("is_html", dict(p["fields"]))

    def test_bad_arguments_still_render(self):
        p = app_preview.build("GMAIL_SEND_EMAIL", "not a dict")
        self.assertEqual(p["title"], "Send email")
        self.assertTrue(p["fields"])


if __name__ == "__main__":
    unittest.main()
