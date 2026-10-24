# Dashboard visual redesign (team-bots shell)

Date: 2026-10-24. Base branch: `feature/team-bots`.
Reference mockup: `2026-10-24-dashboard-redesign-mockup.html` (same folder). Open it in a browser. It loads with the approved settings: **Graphite**, **Compact**, **Light chat**. The picker at the bottom shows the alternatives that were rejected; it is a review aid, not part of the product. The tracked mockup has no web-font links (public-repo network guard), so it renders in the system font; the product uses the self-hosted fonts below.

## Intent

The team-bots branch turned the dashboard into a Slack-style shell (workspace bar, sidebar with channels and teammates, chat, canvas). The structure is close to right, but the look is dated: rust on beige, floating rounded panels, mixed glyph icons, conflicting shapes, tiny labels, no dark mode. The canvas lists posts in one flat list, so the user cannot tell which profile a post belongs to. The chat is visually heavy: every bot message carries tags, tool lines, cost lines, big attachment cards and slide strips.

Goal: a calm, modern, compact team-chat look where posts are clearly divided per profile and the chat is easy to scan, without losing any current capability.

## Goals

1. New visual system: Graphite sidebar, indigo accent, neutral grey surfaces, one icon set, one shape language, light and dark themes.
2. Compact density everywhere (the user found the first proposal "too full or big").
3. Canvas content view groups posts **per profile**, each profile in its own card with a sticky header.
4. Light chat: fewer boxes, less chrome, clear separation between messages.
5. Fix the five usability bugs listed below.

## Non-goals

- No change to the backend data model, osctl, IDs, or file storage.
- No new information architecture beyond what the mockup shows. In particular, the UX Architect's "Option A" ideas are **not** in scope: profiles as chat rooms in the sidebar, a tabbed multi-document canvas, moving Approvals/Team/Calendar out of the canvas into the center pane, unifying the Approvals inbox with post status, per-workspace state restore, `⌘K` search. They may come later as a separate design.
- No new features (no cost meter changes, no new bot capabilities).

## Anti-goals (failure even if it "works")

- Anything that looks green/pine or reintroduces the rust/beige palette.
- Purple-gradient "AI SaaS" look.
- A chat where messages run together (the user flagged this on the light chat: separation must be obvious).
- Losing a current action: every button that exists today (approve, edit, revise, open in canvas, mark ready, schedule, bulk select, filters) must still be reachable.
- Real venture/profile/post names anywhere in tracked files (public repo; `tests/test_no_usage_data.py`).

## Constraints

- Plain HTML/CSS/vanilla JS as today: `dashboard/app.html`, `dashboard/app.css`, `dashboard/ui-tokens.css`, `dashboard/app.js`. No framework, no build step.
- Local-first and works offline: fonts are self-hosted under `dashboard/vendor/fonts/` (woff2, OFL licensed), system font stack as fallback. No runtime Google Fonts request.
- Keep existing `data-*` hooks and `data-os-id` attributes that JS and tests rely on.
- Existing test suite must stay green; run `tests/test_no_usage_data.py` before every commit.
- Work on a branch off `feature/team-bots`. Do **not** merge into `main` or into `feature/team-bots` without the user's go-ahead.

## Decided by the user

### Palette: "Graphite + indigo"

Neutral surfaces (no green tint) in both themes. Values below are the approved mockup values; the full set lives in the mockup's `variant-overrides` block (search `Graphite + indigo`) on top of the UI Designer token sheet.

| Token | Light | Dark |
|---|---|---|
| `--ui-color-rail` (sidebar) | `#17181C` | `#0E0F11` |
| `--ui-color-rail-deep` (workspace bar) | `#0F1013` | `#08090A` |
| `--ui-color-rail-text` / `-muted` | `#B5B9C2` / `#7D828C` | `#B0B3BA` / `#7A7E86` |
| `--ui-color-nav-active` | `#2C2F38` | `#26282E` |
| `--ui-color-accent` / `-hover` | `#4F46E5` / `#4338CA` | `#8B8CF8` / `#A5A6FA` |
| `--ui-color-on-accent` | `#FFFFFF` | `#11122A` |
| `--ui-color-signal` (unread badge) | `#A5B4FC`, ink `#17181C` | same |
| `--ui-color-canvas` / `-surface` / `-surface-subtle` / `-surface-muted` | `#F4F4F6` / `#FFFFFF` / `#F8F8FA` / `#EDEDF0` | `#111214` / `#18191C` / `#1D1F22` / `#26282C` |
| `--ui-color-text` / `-secondary` / `-muted` | `#1B1D22` / `#4A4E57` / `#666B75` | `#E6E7EA` / `#B4B7BE` / `#8D919A` |
| borders / hover | ink `rgba(20,22,28,…)` at 7/12/22% and 4% | white at 6/10/20% and 4% |

Status colors (dot + label, never color alone): idea amber, draft blue, ready violet, published green, archived grey, as in the mockup. Six identity hues for profiles, bots and project tiles (`ocean`, `clay`, `plum`, `ochre`, `slate`, plus a sixth non-green hue to replace `pine`).

### Size: Compact

The mockup reaches "compact" with smaller tokens plus a 92% scale on the whole shell. The build must **not** use `zoom`; bake the result into real sizes:

- Type: body 14px, control 13px, label 12.5px, caption 11.5px, micro 10.5px (only for counters), subtitle 15.5px, title 19px, canvas doc title 25px.
- Radius: inline 4, small 5, control 6, card 8, panel 10; pills only for counters, status and filter chips.
- Sidebar rows 26px, controls 28px (44px on coarse pointers), workspace bar 56px, sidebar 232px, canvas default 540px (still resizable).
- Component padding about 8% tighter than the UI Designer proposal values.

### Light chat

- Every message is a left-aligned row: 24px avatar column (humans round, bots rounded-square in their identity hue with their icon), bold name, muted time, body.
- Removed from the message view: "TEAMMATE" tag, tool-step line, token/cost line, slide thumbnail strip, member-avatar stack in the header, extra composer icons (keep attach and send).
- Deliverable = one slim row: title, subtitle (kind · profile · channels), status pill, "Open in canvas" text button. Slides are seen in the canvas only.
- Approval = one inline row on accent-soft: summary text, **Approve**, **Edit first**, and a quiet ghost **Skip** (today's "No"; it must not be lost).
- Bot consult ("asked by @writer") = indented line with a 2px left rule, no box.
- @mentions = accent-colored bold text, no highlight chip.
- **Message separation:** 12px vertical padding per message, 1px subtle divider between top-level messages, light hover fill on the row, sender name at 13px bold.

### Canvas

Keep the mockup's canvas as is (the user: "the canvas looks way better"):

- White bar with breadcrumb (`acme › Content`), Files, More menu, Close. The "Sections…" select moves into the More menu.
- Document title (serif, Newsreader) + one-line summary ("2 profiles · 6 posts this week · 1 waiting on you").
- Underline tabs: Posts, Calendar, Briefs, Voice. Filter chips with counts: All, Ideas, Drafts, **Ready**, Published.
- **One collapsible card per profile** with a sticky header: avatar in profile hue + hue bar on the left edge, name + mono ID, channel chips, status-mix bar, post count, collapse chevron. Profiles that need the user come first. Empty profiles show "No drafts" inline.
- Post rows inside the card: status pill, format, date; title; two-line excerpt (italic "Not written yet" when empty); slide strip for carousels; next action button, Edit, ID chip. A row opened from chat gets accent-soft fill + accent inset bar + "from @writer, 2m ago".

## Bugs fixed as part of this work

1. "Review →" on a post card approves without opening (`app.js` `NEXT`/`doNext`, ~line 1726). Review must open the post; only an explicit Approve approves.
2. Profile view defaults to the Scheduled filter (~`app.js:1845`), hiding undated bot posts. Default to All.
3. No Ready filter: Ready is folded into Drafts (`STAGE_GROUP`, ~`app.js:1723`). Add a Ready chip and stop folding.
4. Canvas title shows the workspace name instead of what is open (~`app.js:537`). Show a breadcrumb of what is open.
5. Profiles reachable only through the "Sections…" select (~`app.js:531`). The Posts tab now shows every profile, and each profile header links to its full profile page.

Line numbers are approximate pointers from the proposals; verify before editing.

## Claude's calls (settled after the builder check; user may override)

1. **Content view.** New route `#/content` that renders the grouped-per-profile Posts view for the current workspace (in HQ: every project's profiles, grouped by project, then profile). It is the canvas default when the canvas opens with nothing else requested. A post deliverable's "Open in canvas" lands on `#/content` with that post's row focused inside its profile card; clicking the row title (or Review) opens post detail `#/post/<id>` as today. Each profile card header links to the full profile page `#/profile/<slug>`. Content-plan deliverables also land on `#/content`, focused on that profile's card. Canvas breadcrumb reflects the route: `acme › Content`, `acme › profile-a`, `acme › profile-a › po3`.
2. **Canvas tabs reuse existing data, no new screens.** Posts = the Content view. Calendar = the existing calendar view scoped to the current workspace. Briefs and Voice = per-profile lists of brief-specs (`br1`, `br2`…) and voices (`vc1`…), grouped in the same profile cards, each item linking to the existing editor on `#/profile/<slug>/setup`.
3. **Next actions.** Idea: "Write draft" (today's brief generation). Draft: **"Review"**, which opens post detail; approving (status `approved` = Ready) happens only through an explicit Approve button in post detail (fixes bug 1; there is no one-click "Mark ready" from a row). Ready, undated: "Schedule" (opens the date editor). Ready, dated: "Publish" (today's behavior). Rejected: "Restore". Published: no new per-post action ("Log results" in the mockup is out of scope).
4. **Posts tab scope.** All posts, not only this week. Each profile card shows up to 5 rows, then "Show N more". Sort: undated first, then by date descending (today's order). Filter counts cover all posts. Data comes from the existing per-profile endpoint `/api/profile/<slug>/posts`, one call per profile.
5. **"Needs you".** A profile needs the user when it has Drafts waiting for review (status `briefed`). This orders the cards and feeds "N waiting on you". No link to the Approvals inbox (would need backend changes).
6. **Tests.** Tests that encode old behavior get rewritten to the new behavior (e.g. `tests/test_profile_filter_persistence.py` default filter, `tests/test_ui_tokens.py` layout checks). The 3 tests already failing on `feature/team-bots` in `tests/test_ui_tokens.py` get fixed as part of this work. Whole suite green at the end.
7. **Terminal panel.** `#term-panel` stays, same behavior and shortcut, restyled with the new tokens.
8. **Bot progress.** While a bot reply streams, show the live tool-step line and the typing indicator; once the reply is complete they collapse away (light chat hides them only on finished messages).
9. **Fonts.** Self-hosted woff2 in `dashboard/vendor/fonts/`; `server.py`'s `/vendor/` handler must serve `font/woff2`.

## Screens not in the mockup (decided by the user)

- **Re-laid out** with the new components: the full profile page (`#/profile/<slug>`: one profile card using the new post rows, keeping bulk select, channel filter, Add idea, Generate ideas, Setup, Log posted, Write all) and post detail (`#/post/<id>`, including edit/revise and the explicit Approve).
- **Restyle only, layout unchanged:** profile setup, Approvals, Team (memory, costs), Files, Calendar, Today, Operations, project sections, every form, the terminal panel. They pick up the new tokens, buttons, inputs, pills, cards and icons.

## Left to the builder

- How to restructure `app.css` (the proposals suggest `@layer` and deleting the three override layers at roughly `app.css:349-541` and `616-850`); any approach that removes the conflicting layers and most `!important` is fine.
- SVG icon sprite contents (Lucide-style outline, `currentColor`) and the bot `icon`/`hue` mapping, including a fallback for bots without one.
- Exact dark-mode values for status and identity hues, as long as text pairs meet WCAG AA.
- Responsive breakpoints (follow the mockup: canvas becomes an overlay below ~1280px, sidebar becomes a drawer below ~860px).
- Order of work and how to split it into commits.
