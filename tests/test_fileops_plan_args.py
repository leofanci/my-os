import unittest
import dashboard.fileops as fileops

class T(unittest.TestCase):
    def test_requires_period(self):
        with self.assertRaises(fileops.ActionError):
            fileops._plan_args("demo", {})

    def test_full(self):
        args = fileops._plan_args("demo", {"period": "2026-07-01 to 2026-07-14",
                                                     "platforms": "tiktok", "cadence": "3"})
        self.assertIn("plan", args)
        self.assertIn("demo", args)
        self.assertIn("--period", args)

if __name__ == "__main__":
    unittest.main()
