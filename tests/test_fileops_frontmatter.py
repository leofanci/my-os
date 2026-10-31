import contextlib, io, unittest
import dashboard.fileops as fileops


class ParseFrontmatter(unittest.TestCase):
    def test_parses_fields_and_body(self):
        fm, body = fileops._parse_frontmatter("---\nname: demo\n---\nBody\n")
        self.assertEqual((fm, body), ({"name": "demo"}, "Body"))

    def test_broken_opener_warns(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fm, _ = fileops._parse_frontmatter("x---\nname: demo\n---\nBody\n")
        self.assertEqual(fm, {})
        self.assertIn("frontmatter", err.getvalue())

    def test_plain_text_is_silent(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fileops._parse_frontmatter("Just a body.\n\nMore text.")
        self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
