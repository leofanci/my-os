import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CV_JS = ROOT / "dashboard" / "content-view.js"


class TestContentView(unittest.TestCase):
    def run_js(self, expr):
        script = "const CV=require(process.argv[1]);console.log(JSON.stringify(" + expr + "))"
        out = subprocess.run(["node", "-e", script, str(CV_JS)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_next_actions(self):
        self.assertEqual(self.run_js('CV.nextActionFor({status:"planned"})'), {"label": "Write draft", "kind": "brief"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"approved_slot"})'), {"label": "Write draft", "kind": "brief"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"briefed"})'), {"label": "Review", "kind": "review"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"approved",date:null})'), {"label": "Schedule", "kind": "schedule"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"approved",date:"2026-11-02"})'), {"label": "Publish", "kind": "publish"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"rejected"})'), {"label": "Restore", "kind": "restore"})
        self.assertIsNone(self.run_js('CV.nextActionFor({status:"published"})'))
        self.assertIsNone(self.run_js('CV.nextActionFor({status:"unknown"})'))

    def test_ready_is_its_own_group(self):
        self.assertEqual(self.run_js('CV.STAGE_GROUP.approved'), "ready")
        self.assertEqual(self.run_js('CV.STAGE_GROUP.briefed'), "drafts")

    def test_status_pill_and_label(self):
        self.assertEqual(self.run_js('["planned","briefed","approved","published","rejected"].map(s=>CV.STATUS_PILL[s])'),
                         ["idea", "draft", "ready", "published", "archived"])
        self.assertEqual(self.run_js('CV.statusLabel("approved")'), "Ready")
        self.assertEqual(self.run_js('CV.statusLabel("custom")'), "custom")

    def test_sort_undated_first_then_newest(self):
        got = self.run_js('CV.sortPosts([{id:"a",date:"2026-11-01"},{id:"b",date:null},{id:"c",date:"2026-11-03"}]).map(p=>p.id)')
        self.assertEqual(got, ["b", "c", "a"])

    def test_sort_is_stable_and_does_not_mutate(self):
        got = self.run_js('(()=>{const xs=[{id:"a",date:null},{id:"b",date:null},{id:"c",date:"2026-11-01"},{id:"d",date:"2026-11-01"}];'
                          'const out=CV.sortPosts(xs);return [out.map(p=>p.id),xs.map(p=>p.id)]})()')
        self.assertEqual(got, [["a", "b", "c", "d"], ["a", "b", "c", "d"]])

    def test_group_orders_by_needs_you_and_keeps_empty_profiles(self):
        got = self.run_js('CV.groupByProfile(['
            '{id:"1",profile_slug:"profile-a",status:"planned"},'
            '{id:"2",profile_slug:"profile-b",status:"briefed"}],'
            '[{slug:"profile-a",name:"A"},{slug:"profile-b",name:"B"},{slug:"demo",name:"D"}])'
            '.map(g=>[g.profile.slug,g.posts.length,g.needsYou,g.counts.drafts])')
        self.assertEqual(got, [["profile-b", 1, 1, 1], ["profile-a", 1, 0, 0], ["demo", 0, 0, 0]])

    def test_group_counts_every_bucket_and_sorts_posts(self):
        got = self.run_js('CV.groupByProfile(['
            '{id:"1",profile_slug:"profile-a",status:"approved",date:"2026-11-01"},'
            '{id:"2",profile_slug:"profile-a",status:"approved",date:null},'
            '{id:"3",profile_slug:"profile-a",status:"published",date:"2026-10-01"},'
            '{id:"4",profile_slug:"profile-a",status:"rejected",date:null},'
            '{id:"5",profile_slug:"elsewhere",status:"planned"}],'
            '[{slug:"profile-a",name:"A"}])[0]')
        self.assertEqual(got["counts"], {"all": 4, "ideas": 0, "drafts": 0, "ready": 2, "published": 1, "archived": 1})
        self.assertEqual([p["id"] for p in got["posts"]], ["2", "4", "1", "3"])

    def test_empty_inputs(self):
        self.assertEqual(self.run_js('CV.groupByProfile([],[])'), [])

    def test_page_size(self):
        self.assertEqual(self.run_js('CV.PAGE_SIZE'), 5)



class TestContentViewWiring(unittest.TestCase):
    def test_served_loaded_and_used_instead_of_local_copies(self):
        server = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        html = (ROOT / "dashboard" / "app.html").read_text(encoding="utf-8")
        js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"content-view.js"', server)
        self.assertIn('"/content-view.js"', server)
        self.assertLess(html.index('src="/content-view.js"'), html.index('src="/app.js"'))
        self.assertIn("= ContentView;", js)
        for gone in ("const STAGE_GROUP =", "const NEXT =", "function nextActionFor(", "function plainStatus("):
            self.assertNotIn(gone, js)


if __name__ == "__main__":
    unittest.main()
