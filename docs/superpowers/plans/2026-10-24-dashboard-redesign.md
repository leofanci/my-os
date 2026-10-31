# Dashboard Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the team-bots dashboard to the approved Graphite/compact/light-chat design, add a per-profile Content view in the canvas, and fix five usability bugs, without losing any current action.

**Architecture:** Vanilla HTML/CSS/JS as today. Tokens in `dashboard/ui-tokens.css` (light + dark), components in a rewritten `dashboard/app.css`, rendering in `dashboard/app.js`. Pure post-grouping and next-action logic moves to a new UMD module `dashboard/content-view.js` (same pattern as `post-copy.js`) so it can be unit-tested with node. Deliverable links in `dashboard/deliverables.py` point post/plan cards at the new `#/content` route.

**Tech Stack:** Python 3 stdlib server, vanilla JS (ES2020), CSS custom properties, pytest (the system `python3` lacks it; use the local Anaconda `pytest` binary, written `pytest` below) + node for JS unit tests.

**Spec:** `docs/superpowers/specs/2026-10-24-dashboard-redesign-design.md` (reference mockup: `docs/superpowers/specs/2026-10-24-dashboard-redesign-mockup.html`, opens with the approved settings).

## Global Constraints

- Branch `feature/dashboard-redesign` (off `feature/team-bots`). Never merge into `main` or `feature/team-bots` without review.
- Public repo: fixtures and examples use only `demo`, `acme`, `profile-a`, `profile-b`, `@writer`, `@strategist`. Run `python3 -m unittest tests.test_no_usage_data` before every commit.
- No commit trailer `Co-Authored-By` (user preference).
- Never stage `skills/channel-strategy/SKILL.md` (pre-existing local edit, not ours).
- No framework, no build step, no runtime network requests (fonts self-hosted).
- Palette: Graphite + indigo exactly as the spec's table. No green/pine, no rust/beige.
- Compact sizes exactly as the spec's "Size: Compact" list; no CSS `zoom`.
- Keep every existing `data-os-id` attribute and `data-*` hook that JS reads.
- Every current action stays reachable (approve, edit, revise, open in canvas, skip/No, bulk select, filters, channel gear, add idea, generate ideas, setup, log posted, write all, terminal).
- Baseline: `pytest -q -p no:cacheprovider` = 3 failed (all in `tests/test_ui_tokens.py`), 474 passed, 1 skipped. End state: 0 failed.

## Review Focus

1. A workspace with zero profiles, or a profile with zero posts: Content view shows an empty state ("No profiles yet" / "No posts yet" inline in the card), never a blank pane or a JS error. Test in Task 4 (`groupByProfile` with `[]`) and Task 6 (render with no profiles).
2. A post whose `date` is null: sorts at the top of its card, counts under its status filter, and a Ready undated post offers "Schedule", not "Publish". Test in Task 4.
3. A deliverable pointing at a post that is not in the first 5 rows of its card: opening it must expand the card ("Show N more") so the focused row is visible. Test in Task 6.
4. Dark mode chosen by OS setting, and forced by `data-theme`: every token defined in both blocks; no white literal left in `app.css`. Test in Task 1 and Task 3.
5. Narrow window (≤860px) and mid window (≤1280px): sidebar becomes a drawer, canvas becomes an overlay, chat stays usable. Test in Task 3 (CSS assertions) plus the visual check in Task 10.

---

### Task 1: Graphite tokens, compact scale, dark mode

**Files:**
- Modify: `dashboard/ui-tokens.css` (whole file)
- Test: `tests/test_ui_tokens.py`

**Interfaces:**
- Produces: token names used by later tasks. Keep every existing `--ui-*` name currently referenced in `app.css`/`app.js`. Add: `--ui-color-rail-deep`, `--ui-color-rail-text`, `--ui-color-rail-text-strong`, `--ui-color-rail-muted`, `--ui-color-rail-hover`, `--ui-color-signal`, `--ui-color-signal-ink`, `--ui-color-on-accent`, `--ui-color-accent-line`, `--ui-color-border-strong`, `--ui-status-{idea,draft,ready,published,archived}` (+ `-soft`), `--ui-id-{ocean,clay,plum,ochre,slate,rose}-{bg,fg}`, `--ui-radius-avatar-bot`, `--ui-font-display`, `--ws-bar-w`, `--canvas-w`, `--ui-breakpoint-canvas-overlay: 1280px`, `--ui-breakpoint-nav-drawer: 860px`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ui_tokens.py`

```python
def _tokens():
    return (DASHBOARD / "ui-tokens.css").read_text(encoding="utf-8")

def test_graphite_palette_light():
    t = _tokens()
    for decl in ("--ui-color-rail: #17181C", "--ui-color-rail-deep: #0F1013",
                 "--ui-color-accent: #4F46E5", "--ui-color-canvas: #F4F4F6",
                 "--ui-color-surface: #FFFFFF", "--ui-color-text: #1B1D22"):
        assert decl.replace(" ", "") in t.replace(" ", "")

def test_dark_mode_blocks_exist_and_redefine_accent():
    t = _tokens()
    assert '@media (prefers-color-scheme:dark)' in t.replace(": ", ":")
    assert ':root:not([data-theme="light"])' in t
    assert ':root[data-theme="dark"]' in t
    assert t.replace(" ", "").count("--ui-color-accent:#8B8CF8") == 2

def test_compact_type_and_radius_scale():
    t = _tokens().replace(" ", "")
    for decl in ("--ui-type-body:14px", "--ui-radius-card:8px", "--ui-radius-control:6px",
                 "--ui-control-default:28px", "--ws-bar-w:56px", "--canvas-w:540px"):
        assert decl in t

def test_no_green_or_rust_left():
    t = _tokens().upper()
    for banned in ("#10302A", "#1F6F5C", "#B54A2B", "#F3F2EF"):
        assert banned not in t
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py`
Expected: the 4 new tests FAIL; the 3 baseline failures still fail.

- [ ] **Step 3: Rewrite `dashboard/ui-tokens.css`**

Values: the spec's palette table (light + dark), status and identity hues from the mockup token block (replace `pine` with a sixth hue `rose`: bg `#F6E0E7`, fg `#8E2A4B`; dark bg `#3F1E2A`, fg `#F2A9C0`), compact type/radius/size list from the spec. Dark values appear twice: under `@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){…} }` and under `:root[data-theme="dark"]{…}`. Keep the existing `--ui-kind-*` and `--ui-color-{warning,success}-soft` tokens (WCAG tests read them) and the compatibility aliases block, repointed to the new values. Add `@font-face` rules at the top for `Instrument Sans` (400, 500, 600, 700), `Newsreader` (500, 600) and `JetBrains Mono` (500) at `/vendor/fonts/<family>-<weight>.woff2` with `font-display:swap` (files land in Task 2).

- [ ] **Step 4: Run the whole token test file**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py`
Expected: new tests PASS; both WCAG tests PASS (adjust only a failing value's lightness, never the hue family); `test_all_css_custom_properties_resolve` PASSES now that `--ws-bar-w` and `--canvas-w` are defined. `test_layout_javascript_reads_css_tokens` and `test_assistant_becomes_overlay…` are rewritten in Task 3.

- [ ] **Step 5: Commit**

```bash
git add dashboard/ui-tokens.css tests/test_ui_tokens.py
git commit -m "Tokens: graphite palette, compact scale, dark mode"
```

---

### Task 2: Self-hosted fonts and SVG icon sprite

**Files:**
- Create: `dashboard/vendor/fonts/*.woff2`, `dashboard/vendor/fonts/OFL.txt`
- Modify: `dashboard/server.py` (`/vendor/` handler ~line 1429), `dashboard/app.html`, `dashboard/app.js` (new `icon()` helper near `esc`; `renderWsBar`, `renderRail`, `KIND_META`, `PLATFORM_ICON`, `KIND_ICON`)
- Test: `tests/test_ui_tokens.py`, `tests/test_security_boundaries.py` (pattern for HTTP tests)

**Interfaces:**
- Produces: `icon(name: string, cls?: string) -> string` returning `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`. Sprite symbol ids: `i-hash, i-inbox, i-folder, i-users, i-sun, i-calendar, i-list-check, i-plus, i-compose, i-search, i-menu, i-threads, i-panel, i-x, i-clip, i-send, i-check, i-layers, i-doc, i-chart, i-pen, i-compass, i-flask, i-map, i-route, i-clock, i-reply, i-gear, i-chevron, i-more, i-moon, i-terminal, i-instagram, i-tiktok, i-linkedin, i-x-brand, i-youtube, i-facebook`.

- [ ] **Step 1: Write the failing tests**

```python
def test_vendor_serves_woff2_as_font():
    server = (DASHBOARD / "server.py").read_text(encoding="utf-8")
    assert '"font/woff2"' in server

def test_fonts_are_vendored():
    fonts = DASHBOARD / "vendor" / "fonts"
    for name in ("instrument-sans-400.woff2", "instrument-sans-600.woff2",
                 "newsreader-600.woff2", "jetbrains-mono-500.woff2", "OFL.txt"):
        assert (fonts / name).is_file(), name

def test_sprite_and_no_glyph_icons_in_shell():
    html = (DASHBOARD / "app.html").read_text(encoding="utf-8")
    js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert '<symbol id="i-inbox"' in html
    for glyph in ("✔", "☰", "◆", "▦", "▣", "⊕", "📄", "⚗", "📘", "🗓"):
        assert glyph not in html and glyph not in js, glyph
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py -k "woff2 or vendored or sprite"`
Expected: 3 FAIL.

- [ ] **Step 3: Download fonts** (one-time, at build time only) from `https://cdn.jsdelivr.net/npm/@fontsource/<family>/files/<family>-latin-<weight>-normal.woff2` for instrument-sans 400/500/600/700, newsreader 500/600, jetbrains-mono 500; save as `dashboard/vendor/fonts/<family>-<weight>.woff2`; add the SIL OFL 1.1 text as `OFL.txt`. No URL to these hosts may be committed (privacy guard).

- [ ] **Step 4: Server** — in the `/vendor/` handler map `.woff2` to `"font/woff2"`, `.txt` to `"text/plain"`, keep css/js mapping.

- [ ] **Step 5: Sprite + glyph swap** — inline `<svg width="0" height="0" style="position:absolute" aria-hidden="true">` with the symbol ids above (Lucide-style 24-unit outline paths, `stroke="currentColor"`, `stroke-width="1.75"`, `fill="none"`) at the top of `<body>` in `app.html`. Replace every glyph in `app.html` buttons and in `renderWsBar`, `renderRail`, `KIND_META` (value becomes an icon name), `PLATFORM_ICON`, `KIND_ICON`, terminal chevron, canvas close, `addStep` "⚙". Workspace "+" uses `icon("plus")`.

- [ ] **Step 6: Run tests**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py tests/test_security_boundaries.py`
Expected: PASS (except the two layout tests owned by Task 3).

- [ ] **Step 7: Commit**

```bash
git add dashboard/vendor/fonts dashboard/server.py dashboard/app.html dashboard/app.js tests/test_ui_tokens.py
git commit -m "Self-hosted fonts and SVG icon sprite"
```

---

### Task 3: Shell layout, sidebar, responsive CSS rewrite

**Files:**
- Modify: `dashboard/app.css` (rewrite), `dashboard/app.js` (`renderRail` ~446-505, canvas code ~3104-3135), `dashboard/app.html`
- Test: `tests/test_ui_tokens.py`

**Interfaces:**
- Consumes: Task 1 tokens, Task 2 `icon()`.
- Produces: CSS classes used by Tasks 6-9: `.btn`, `.btn.primary`, `.btn.ghost`, `.btn.sm`, `.chip`, `.stp.{idea,draft,ready,published,archived}` (status pill: dot + label), `.av`, `.av.bot`, `.av.t-{ocean,clay,plum,ochre,slate,rose}`, `.mono`, `.card`, `.empty`.

- [ ] **Step 1: Rewrite the two stale tests and add layout assertions**

Replace `test_layout_javascript_reads_css_tokens` and `test_assistant_becomes_overlay_before_workspace_is_cramped` with:

```python
def test_canvas_js_reads_css_tokens():
    js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert 'cssPx("--canvas-w"' in js
    assert 'cssPx("--ui-breakpoint-canvas-overlay", 1280)' in js

def test_responsive_breakpoints():
    css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    assert "@media (max-width:1280px)" in css   # canvas becomes overlay
    assert "@media (max-width:860px)" in css    # sidebar becomes drawer

def test_css_debt_removed():
    css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    assert css.count("!important") <= 4
    assert "#fff" not in css.lower() and "#ffffff" not in css.lower()
    assert "translateX(2px)" not in css
    assert "border-radius:999px;padding:" not in css.replace(" ", "")  # no pill buttons

def test_sidebar_sections_renamed():
    js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert ">Teammates<" in js and ">Direct messages<" not in js
```

Keep `test_filter_chips_use_pointer_appropriate_targets` and `test_project_edit_action_reveals_on_actual_row_hover` unchanged; the rewrite must keep those exact rules.

- [ ] **Step 2: Run to verify the new ones fail**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py`
Expected: the 4 tests above FAIL.

- [ ] **Step 3: Rewrite `app.css`** against tokens: edge-to-edge panes with 1px dividers (no floating cards, no gaps), workspace bar on `--ui-color-rail-deep`, sidebar on `--ui-color-rail`, chat sheet on surface, canvas on canvas color; shared components listed in Interfaces; drop the three override layers (old lines ~349-541 and ~616-850). Sizes from the spec's compact list. Breakpoints: ≤1280px canvas `position:fixed` right overlay with `--ui-shadow-menu`; ≤860px workspace bar folds into the sidebar and the sidebar becomes a left drawer opened by a hamburger in the chat header (`#nav-toggle`, new button).

- [ ] **Step 4: Update `renderRail`** — header (workspace name + caret menu, compose button), utility rows Approvals (signal badge) / Files / Team, collapsible sections "Channels", "Teammates" (was "Direct messages"), "Your time"; bot rows show `.av.bot` in the bot's hue with its icon; section collapse state stored in `localStorage` key `railCollapsed` inside try/catch. Canvas code reads `--canvas-w` default and the overlay breakpoint via `cssPx`.

- [ ] **Step 5: Run tests**

Run: `pytest -q -p no:cacheprovider`
Expected: 0 failed.

- [ ] **Step 6: Visual check** — `python3 dashboard/server.py`, open the printed login link, compare shell against the mockup at 1440, 1000 and 390px wide, light and dark (`document.documentElement.dataset.theme='dark'` in devtools).

- [ ] **Step 7: Commit**

```bash
git add dashboard/app.css dashboard/app.js dashboard/app.html tests/test_ui_tokens.py
git commit -m "Shell: edge-to-edge layout, graphite sidebar, responsive drawer and overlay"
```

---

### Task 4: `content-view.js` post logic (statuses, next actions, grouping)

**Files:**
- Create: `dashboard/content-view.js`
- Modify: `dashboard/app.js` (delete `STAGE_GROUP`, `NEXT`, `nextActionFor` at ~1723-1741; use `ContentView.*`), `dashboard/app.html` (script tag before `app.js`), `dashboard/server.py` (add `"content-view.js"` to both static allowlists at ~157 and ~1413)
- Test: `tests/test_content_view.py` (node subprocess, same harness as `tests/test_post_copy.py`)

**Interfaces:**
- Produces (global `ContentView`, also `module.exports`):
  - `STAGE_GROUP: {planned:"ideas", approved_slot:"ideas", briefed:"drafts", approved:"ready", published:"published", rejected:"archived"}`
  - `nextActionFor(post) -> null | {label, kind}` where `kind` ∈ `"brief" | "review" | "schedule" | "publish" | "restore"`
  - `sortPosts(posts) -> posts` (undated first, then date descending; stable)
  - `groupByProfile(posts, profiles) -> [{profile, posts, counts:{all,ideas,drafts,ready,published,archived}, needsYou:number}]`; `profiles` is `[{slug, name, channels}]`; `needsYou` = count of status `briefed`; groups ordered by `needsYou` desc, then original profile order; every profile appears, even with no posts.
  - `PAGE_SIZE = 5`

- [ ] **Step 1: Write the failing tests**

```python
class TestContentView(unittest.TestCase):
    def run_js(self, expr):
        script = "const CV=require(process.argv[1]);console.log(JSON.stringify(" + expr + "))"
        out = subprocess.run(["node", "-e", script, str(CV_JS)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_next_actions(self):
        self.assertEqual(self.run_js('CV.nextActionFor({status:"planned"})'), {"label": "Write draft", "kind": "brief"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"briefed"})'), {"label": "Review", "kind": "review"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"approved",date:null})'), {"label": "Schedule", "kind": "schedule"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"approved",date:"2026-11-02"})'), {"label": "Publish", "kind": "publish"})
        self.assertEqual(self.run_js('CV.nextActionFor({status:"rejected"})'), {"label": "Restore", "kind": "restore"})
        self.assertIsNone(self.run_js('CV.nextActionFor({status:"published"})'))

    def test_ready_is_its_own_group(self):
        self.assertEqual(self.run_js('CV.STAGE_GROUP.approved'), "ready")

    def test_sort_undated_first_then_newest(self):
        got = self.run_js('CV.sortPosts([{id:"a",date:"2026-11-01"},{id:"b",date:null},{id:"c",date:"2026-11-03"}]).map(p=>p.id)')
        self.assertEqual(got, ["b", "c", "a"])

    def test_group_orders_by_needs_you_and_keeps_empty_profiles(self):
        got = self.run_js('CV.groupByProfile(['
            '{id:"1",profile_slug:"profile-a",status:"planned"},'
            '{id:"2",profile_slug:"profile-b",status:"briefed"}],'
            '[{slug:"profile-a",name:"A"},{slug:"profile-b",name:"B"},{slug:"demo",name:"D"}])'
            '.map(g=>[g.profile.slug,g.posts.length,g.needsYou,g.counts.drafts])')
        self.assertEqual(got, [["profile-b", 1, 1, 1], ["profile-a", 1, 0, 0], ["demo", 0, 0, 0]])

    def test_empty_inputs(self):
        self.assertEqual(self.run_js('CV.groupByProfile([],[])'), [])
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_content_view.py`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `dashboard/content-view.js`** as a UMD module copying the wrapper of `post-copy.js`; wire it into `app.html`, both server allowlists, and replace the old constants in `app.js` (`STAGE_GROUP`, `nextActionFor`; `doNext` switches on `kind`: `brief` → existing brief POST, `review` → `navigate("#/post/<id>")`, `schedule` → `navigate("#/post/<id>/edit")`, `publish`/`restore` → existing status POST with `published`/`planned`).

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider tests/test_content_view.py tests/test_post_copy.py tests/test_security_boundaries.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/content-view.js dashboard/app.js dashboard/app.html dashboard/server.py tests/test_content_view.py
git commit -m "ContentView: Ready group, review-opens-post next actions, per-profile grouping"
```

---

### Task 5: Deliverable links point at the Content view

**Files:**
- Modify: `dashboard/deliverables.py` (`describe` ~lines 101-111, `_collapse` ~139-143)
- Test: `tests/test_deliverables.py`

**Interfaces:**
- Produces: deliverable items consumed by Task 6's `openDeliverable`:
  - content plan: `{"kind":"content", "link":"#/content", "focus": <profile composed id or None>, "profile": prof}`
  - single post brief: `{"kind":"brief", "link":"#/content", "focus": <post composed id>, "profile": prof, "post": pid}`
  - collapsed briefs: `{"kind":"brief", "link":"#/content", "focus": <profile composed id or None>, "profile": prof}`

- [ ] **Step 1: Write the failing tests** (in `test_kinds_and_links` and the collapse test)

```python
self.assertEqual(items["content:profile-a"]["link"], "#/content")
self.assertEqual(items["content:profile-a"]["profile"], "profile-a")
# in test_changed_only_reports_this_turn_and_collapses_briefs:
card = next(i for i in got if i["kind"] == "brief")
self.assertEqual(card["link"], "#/content")
self.assertEqual(card["profile"], "profile-a")
```

plus a single-brief case asserting `link == "#/content"` and `post == "p1"`.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_deliverables.py`
Expected: FAIL on link values.

- [ ] **Step 3: Implement** the link changes; for the profile focus use the registry's profile id lookup the same way `lk_post` is used (falls back to `None` when the registry is missing).

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider tests/test_deliverables.py tests/test_teammates.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/deliverables.py tests/test_deliverables.py
git commit -m "Deliverables: post and plan cards open the Content view"
```

---

### Task 6: Content route, canvas bar, profile cards

**Files:**
- Modify: `dashboard/app.js` (`ROUTES` ~190, `renderCanvasNav` ~524, `setFocus`/`openDeliverable` ~557-580, `switchWorkspace` ~432, new `renderContent`, new `postRowHtml`, new `profileCardHtml`), `dashboard/app.css`
- Test: `tests/test_content_route.py` (static source assertions, same style as `tests/test_profile_filter_persistence.py`)

**Interfaces:**
- Consumes: `ContentView.groupByProfile`, `sortPosts`, `nextActionFor`, `PAGE_SIZE`, `STAGE_GROUP` (Task 4); deliverable shape (Task 5); CSS components (Task 3).
- Produces:
  - Route `#/content` and `#/content/<tab>` with `tab` ∈ `posts | calendar | briefs | voice` (default `posts`).
  - `renderContent(tab: string) -> Promise<void>` renders into `#main`.
  - `postRowHtml(post, channels, opts:{selectable:boolean, focused:boolean}) -> string`, root `<div class="post-row" data-post="<id>">`, used again by Task 7.
  - `profileCardHtml(group, opts:{limit:number, filter:string, focusId:string|null}) -> string`, root `<details class="pf" open data-profile="<slug>">` with a `<summary class="pf-head">` (sticky).
  - `CONTENT_FILTER` module-level state, values `all | ideas | drafts | ready | published`.

- [ ] **Step 1: Write the failing tests**

```python
def test_content_route_and_tabs():
    js = APP_JS.read_text(encoding="utf-8")
    assert r"/^\/content(?:\/(posts|calendar|briefs|voice))?$/" in js
    assert "async function renderContent(tab" in js
    assert 'data-f="ready"' in js

def test_canvas_bar_shows_breadcrumb_not_sections_select():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'class="cn-crumb"' in js
    assert '<option value="">Sections…</option>' not in js   # moved into the More menu
    assert 'data-cn-more' in js

def test_focus_expands_card_beyond_page_size():
    js = APP_JS.read_text(encoding="utf-8")
    assert "focusId" in js and "PAGE_SIZE" in js
    assert 'card.querySelector(".pf-more")' in js or "limit: Infinity" in js

def test_workspace_switch_lands_on_content():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'navigate(ws === "hq" ? "#/calendar" : "#/content")' in js
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_content_route.py`
Expected: FAIL.

- [ ] **Step 3: Implement**
  - Data: profiles of the workspace project(s) from `_TREE` (HQ: every project, rendered as one `<section>` per project with the project name as heading); posts from `/api/profile/<slug>/posts` per profile, fetched in parallel.
  - Posts tab: serif title "Content", summary line `"<n> profiles · <m> posts · <k> waiting on you"`, underline tabs, filter chips All/Ideas/Drafts/Ready/Published with counts across all groups, then one `profileCardHtml` per group. Card header: avatar in profile hue (hue by profile index over the 6 identity hues), name + mono composed id, channel chips, status-mix bar (widths from `counts`), post count, chevron; name links to `#/profile/<slug>`. Empty profile: `<div class="empty">No posts yet</div>`; filter leaves nothing: "No drafts" etc. Rows: first `PAGE_SIZE`, then `<button class="pf-more">Show N more</button>`.
  - Focus: `openDeliverable` keeps passing `focus`; when a focus id belongs to a post in a card, render that card with `limit: Infinity`, scroll the row into view, add class `focused` (accent-soft fill, 3px accent inset, "from @bot, Nm ago" when the deliverable carries a bot). `setFocus` stops hiding non-focused groups on `#/content`. Remove the `.flash` ring.
  - Calendar tab: call `renderTimeline({scope})` where `scope` is a Set of the workspace's project, profile and product slugs; rows filter on `entity_slug`. HQ: no scope.
  - Briefs / Voice tabs: one card per profile listing its brief-specs / voices (existing `/api/profile/<slug>/brief-specs` and `/voices` GET routes in `server.py` ~1537), each item linking to `#/profile/<slug>/setup`.
  - `renderCanvasNav`: breadcrumb `<span class="cn-crumb">workspace › page › item</span>` from the route (Content, profile name, post composed id, section label, Files…), Files ghost button, More menu (`data-cn-more`) holding the old Sections list, profiles, Project settings, Show all, then Close.
  - `switchWorkspace` lands on `#/content` for project workspaces; the canvas toggle opens `#/content` when nothing is routed.

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider`
Expected: 0 failed.

- [ ] **Step 5: Visual check** against the mockup canvas: two profiles, one with 7 posts (Show 2 more), one empty; open a post deliverable whose row is 7th, the row is visible and highlighted.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js dashboard/app.css tests/test_content_route.py
git commit -m "Canvas: Content view with per-profile cards, breadcrumb, More menu"
```

---

### Task 7: Profile page and post detail re-layout

**Files:**
- Modify: `dashboard/app.js` (`renderProfile` ~1833-1966, `renderPostDetail` ~2333-2390), `dashboard/app.css`
- Test: `tests/test_profile_filter_persistence.py`, `tests/test_content_route.py`

**Interfaces:**
- Consumes: `postRowHtml`, `profileCardHtml` (Task 6), `ContentView.*` (Task 4).

- [ ] **Step 1: Update the tests**

In `tests/test_profile_filter_persistence.py` the default becomes `"all"`:

```python
self.assertRegex(source, r'let FILTER\s*=\s*PROFILE_FILTER\[slug\]\s*\|\|\s*"all";')
self.assertIn('data-f="ready"', source)
```

(keep the `unscheduled` chip assertion; drop nothing else). Add to `tests/test_content_route.py`:

```python
def test_post_detail_has_explicit_approve_for_drafts():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'id="approvePost"' in js
    assert 'status:"approved"' in js.replace(" ", "")

def test_profile_page_keeps_every_action():
    js = APP_JS.read_text(encoding="utf-8")
    for hook in ('id="addIdea"', 'id="genIdeas"', 'id="setupBtn"', 'id="logPosted"',
                 'id="writeAll"', 'class="chan-gear"', 'data-sel=', 'id="addChanBtn"'):
        assert hook in js, hook
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_profile_filter_persistence.py tests/test_content_route.py`
Expected: FAIL on default filter, Ready chip, approve button.

- [ ] **Step 3: Implement**
  - `renderProfile`: page = one profile card (same header as Task 6, not collapsible) holding the channel chips with gear, topic, actions (Add idea, Generate ideas primary, More: Setup/Log posted/Write all ideas), filter chips Scheduled/All/Ideas/Drafts/Ready/Published/Unscheduled with default `all`, then `postRowHtml(..., {selectable:true})` rows (no page limit). Bulk-select bar uses classes, no inline colors.
  - `renderPostDetail`: header with status pill + format + date, title, actions bar: for `briefed` an explicit `<button class="btn primary" id="approvePost">Approve</button>` posting `{status:"approved"}`, plus Edit and Revise; for other statuses the `nextActionFor` button. Body sections (brief, slides) restyled with the card component.

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider`
Expected: 0 failed.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js dashboard/app.css tests/test_profile_filter_persistence.py tests/test_content_route.py
git commit -m "Profile page and post detail on the new post rows; explicit Approve"
```

---

### Task 8: Light chat

**Files:**
- Modify: `dashboard/app.js` (`botLabel` ~3600, `decorateReply` ~3614, `addMsg` ~3651, `addStep`/`finalizeSteps` ~3670-3700, `showChat` ~3259, room header members), `dashboard/app.html` (chat header), `dashboard/app.css`
- Test: `tests/test_chat_light.py` (static source assertions)

**Interfaces:**
- Consumes: `icon()`, `.av` classes, deliverable shape from Task 5, `openDeliverable` from Task 6.
- Produces: message markup `<div class="msg"><span class="av …"></span><div class="msg-main"><div class="mh"><b>name</b><time></time></div><div class="b"></div></div></div>`; `addMsg(role, text, bot, askedBy, ts)` gains a trailing optional `ts` (seconds); `.b` stays the element returned so streaming code keeps working.

- [ ] **Step 1: Write the failing tests**

```python
def test_message_row_structure():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'class="msg-main"' in js and 'class="mh"' in js
    assert "function addMsg(role, text, bot, askedBy, ts)" in js

def test_usage_moves_to_tooltip_and_steps_vanish_when_done():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'meta.className = "msg-meta"' not in js
    assert "stepEl.remove()" in js

def test_deliverable_row_and_approval_row_keep_all_actions():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'class="deliv-row"' in js and ">Open in canvas<" in js
    for act in ('data-ap="approved"', 'data-ap="edit"', 'data-ap="rejected"'):
        assert act in js
    assert ">Skip<" in js

def test_messages_are_separated():
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
    assert ".msg+.msg{border-top:1px solid var(--ui-color-border-subtle)}" in css.replace(" ", "")
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest -q -p no:cacheprovider tests/test_chat_light.py`
Expected: FAIL.

- [ ] **Step 3: Implement** per the spec's "Light chat" list:
  - Every message (user too) is a left-aligned row: 24px avatar (user: round with initial of "You"; bot: rounded-square in bot hue with bot icon), bold name 13px, muted time from `ts` (`HH:MM`, omitted when missing), body.
  - `botLabel` fills `.mh` (name, "from @x" / "asked by @x" muted) instead of prepending a label; consults get class `consulted` → indented with a 2px left rule, no box.
  - `decorateReply`: no visible usage line (put usage into the `title` of `<time>`); deliverables become `<div class="deliv-row">` with title, subtitle `"<kind label> · <profile name>"`, status pill when present, and a text button "Open in canvas"; approval becomes one row on accent-soft with summary, Approve (primary), Edit first (secondary), Skip (ghost, `data-ap="rejected"`, sends today's "No, skip it.").
  - Steps: live "working… N steps" line and typing indicator while streaming; `finalizeSteps` removes the line (`stepEl.remove()`).
  - Header: hide the member stack; mentions render as accent bold text.
  - CSS: 12px vertical padding per message, `.msg+.msg` 1px subtle divider, hover fill, composer one bordered box with attach + send.

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider`
Expected: 0 failed.

- [ ] **Step 5: Visual check** — send a message to a bot in a demo workspace; compare to the mockup's Light chat (separation visible, slim deliverable row, one-line approval).

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js dashboard/app.html dashboard/app.css tests/test_chat_light.py
git commit -m "Light chat: avatar rows, slim deliverables and approvals, clear separation"
```

---

### Task 9: Restyle sweep for the remaining screens

**Files:**
- Modify: `dashboard/app.js` (inline `style="…"` attributes in render functions for Approvals, Team, Files, Calendar, Today, Operations, project sections, forms, profile setup, terminal panel), `dashboard/app.css`
- Test: `tests/test_ui_tokens.py`

- [ ] **Step 1: Write the failing test**

```python
def test_no_hardcoded_colors_in_rendered_markup():
    js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    styles = re.findall(r'style="([^"]*)"', js)
    colored = [s for s in styles if re.search(r"#[0-9A-Fa-f]{3,6}\b|rgba?\(", s)]
    assert colored == [], colored[:5]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q -p no:cacheprovider tests/test_ui_tokens.py -k hardcoded`
Expected: FAIL listing inline colors (e.g. the bulk-select bar).

- [ ] **Step 3: Implement** — move every colored inline style into classes that use tokens; layouts of these screens stay as they are. Forms: 32px inputs, 6px radius, 12.5px sentence-case labels. Terminal keeps its tokens (`--ui-color-terminal`, `--ui-terminal-font-size`).

- [ ] **Step 4: Run tests**

Run: `pytest -q -p no:cacheprovider`
Expected: 0 failed.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js dashboard/app.css tests/test_ui_tokens.py
git commit -m "Restyle remaining screens with tokens; no inline colors"
```

---

### Task 10: Final verification

- [ ] **Step 1: Full suite** — `pytest -q -p no:cacheprovider` → 0 failed; `python3 -m unittest tests.test_no_usage_data tests.test_security_boundaries` → OK.
- [ ] **Step 2: Visual pass** — run the dashboard with a demo workspace (fixtures only) and screenshot every screen (shell, Content Posts/Calendar/Briefs/Voice, profile page, post detail, Approvals, Team, Files, Calendar, Today, Operations, one form, terminal open) at 1440px light, 1440px dark, 1000px, 390px. Compare against the mockup; fix anything off before reporting.
- [ ] **Step 3: Report** — branch name, commits, test output summary, screenshots path. Do not merge.
