import json
import tempfile
import unittest
from pathlib import Path

import index
from tests.test_index_projects import write
import dashboard.fileops as fileops
import dashboard.db as db
from core import gtm
from core.ids import build_id_registry, lk_phase, lk_strategy


class GtmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        proj = self.root / "projects" / "acme"
        write(proj / "project.md",
              "---\nname: Acme\nkind: venture\npriority: primary\n"
              "status: idea\nhours_per_week: 5\n---\nvoice")
        fileops.ROOT = self.root
        db.DB_PATH = self.root / "database" / "data" / "os.db"
        index.build(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _reg(self):
        return build_id_registry(db.tree(), db.posts(), root=self.root)

    # ---- storage + normalize ---------------------------------------------- #
    def test_create_phase_and_strategy_round_trip(self):
        fileops.create_phase("acme", "First 10 customers", goal="10 paying")
        phases = gtm.load_phases(self.root, "acme")
        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0]["id"], "first-10-customers")
        self.assertEqual(phases[0]["status"], "planned")

        fileops.create_strategy("acme", "first-10-customers", "acme-linkedin",
                                "founders reply to DMs", name="LinkedIn outbound",
                                primary=True)
        strats = gtm.load_strategies(self.root, "acme")
        self.assertEqual(len(strats), 1)
        self.assertEqual(strats[0]["stem"], "linkedin-outbound")
        self.assertEqual(strats[0]["phase"], "first-10-customers")
        self.assertTrue(strats[0]["primary"])
        self.assertEqual(strats[0]["channel_slug"], "acme-linkedin")

    # ---- composed id cascade ---------------------------------------------- #
    def test_phase_strategy_composed_ids(self):
        fileops.create_phase("acme", "First 10 customers")
        fileops.create_strategy("acme", "first-10-customers", "", "test", name="Motion A")
        reg = self._reg()
        ph = reg.get(lk_phase("acme", "first-10-customers"))
        st = reg.get(lk_strategy("acme", "motion-a"))
        self.assertRegex(ph, r"^pr1\.sec07\.ph1$")
        self.assertRegex(st, r"^pr1\.sec07\.ph1\.st1$")

    def test_unphased_strategy_hangs_under_gtm_tab(self):
        fileops.create_strategy("acme", "", "", "test", name="Loose")
        reg = self._reg()
        st = reg.get(lk_strategy("acme", "loose"))
        self.assertRegex(st, r"^pr1\.sec07\.st1$")

    # ---- the lens: experiment tags up to a strategy ----------------------- #
    def test_experiment_strategy_tag_and_view(self):
        fileops.create_phase("acme", "First 10 customers")
        fileops.create_strategy("acme", "first-10-customers", "", "hyp", name="LinkedIn")
        fileops.create_experiment("acme", {"assumption": "DMs convert",
                                           "stem": "exp-dm", "strategy": "linkedin"})
        body = json.loads((self.root /
            "projects/acme/strategy/experiments/exp-dm.json").read_text())
        self.assertEqual(body["strategy"], "linkedin")

        data = db.project("acme")
        for x in data["experiments"]:
            x["body"] = fileops.read_authored_json(x.get("file_path"))
        view = gtm.build_view(self.root, "acme", self._reg(), data["experiments"])
        self.assertEqual(len(view["phases"]), 1)
        strat = view["phases"][0]["strategies"][0]
        self.assertEqual(strat["stem"], "linkedin")
        self.assertEqual(len(strat["experiments"]), 1)
        self.assertEqual(strat["experiments"][0]["stem"], "exp-dm")

    def test_experiment_tag_unknown_strategy_rejected(self):
        with self.assertRaises(fileops.ActionError):
            fileops.create_experiment("acme", {"assumption": "x", "strategy": "ghost"})

    # ---- delete + primary invariant --------------------------------------- #
    def test_delete_strategy_and_phase(self):
        fileops.create_phase("acme", "P1")
        fileops.create_strategy("acme", "p1", "", "h", name="S1")
        fileops.delete_strategy("acme", "s1")
        self.assertEqual(gtm.load_strategies(self.root, "acme"), [])
        fileops.delete_phase("acme", "p1")
        self.assertEqual(gtm.load_phases(self.root, "acme"), [])

    def test_only_one_primary(self):
        fileops.create_strategy("acme", "", "", "h", name="A", primary=True)
        fileops.create_strategy("acme", "", "", "h", name="B", primary=True)
        strats = {s["stem"]: s for s in gtm.load_strategies(self.root, "acme")}
        self.assertFalse(strats["a"]["primary"])
        self.assertTrue(strats["b"]["primary"])


if __name__ == "__main__":
    unittest.main()
