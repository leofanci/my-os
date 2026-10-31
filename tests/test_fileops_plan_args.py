import unittest
import dashboard.fileops as fileops
import generate

class T(unittest.TestCase):
    def test_requires_period(self):
        with self.assertRaises(fileops.ActionError):
            fileops._plan_args("demo", {})

    def test_full(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14",
                                                     "platforms": "tiktok", "cadence": "3"})
        self.assertIn("plan", args)
        self.assertIn("demo", args)
        self.assertIn("--period=2026-07-01 to 2026-07-14", args)

    def test_free_text_stays_a_value_in_generate_parser(self):
        # Option-looking text ("--dates", "-x") must reach the job as text, not
        # flip a flag or fail the parse.
        args = fileops._plan_args("demo", {"period": "--dates", "focus": "--dates -x",
                                            "platforms": "--cadence"})
        parsed = generate.build_parser().parse_args(args[2:])
        self.assertEqual((parsed.period, parsed.focus, parsed.platforms, parsed.dates),
                         ("--dates", "--dates -x", "--cadence", False))

    def test_dates_flag_forwarded_when_set(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14",
                                            "dates": True})
        self.assertIn("--dates", args)

    def test_dates_flag_omitted_by_default(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14"})
        self.assertNotIn("--dates", args)

if __name__ == "__main__":
    unittest.main()
