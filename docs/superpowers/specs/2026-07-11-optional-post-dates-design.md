# Optional post dates + unscheduled bucket — design

**Date:** 2026-07-11
**Scope:** Post `date` becomes opt-in at generation time instead of always assigned. Undated posts can still be written and reviewed but not published. Dates can be cleared on any non-published post. A new global nav view surfaces every undated, non-published post across all profiles.

## Problem

`generate.py do_plan` always asks Claude to assign a `date` (`YYYY-MM-DD`) to every minted post (`prompts/plan.txt` schema), spread across the requested period. There is no way to generate a batch of ideas without dates, no gate preventing an undated post from being published, and no dedicated place to find posts that never got a date (they're mixed into the profile's Ideas/Drafts filters with no way to isolate them). `date` is already optional in storage (`dashboard/fileops.py` docstring: `date?`; `update_post` already drops the field when written empty) — the gap is entirely in generation, publish validation, and discoverability.

## Design

### 1. Generation: dates opt-in

- `generate.py do_plan(root, profile_slug, period, platforms, cadence, focus, brief_counts=None, voice_counts=None, assign_dates=False)` — new keyword, default `False`.
- `prompts/plan.txt` params block gains a line reflecting the flag, e.g. `dates: assign one YYYY-MM-DD per post, spread across the period` (when True) or `dates: do NOT include a "date" field on any post — leave every post unscheduled` (when False).
- Defense in depth: after `run_job`, in the same loop that already forces `post["status"] = "planned"`, strip `post.pop("date", None)` when `assign_dates` is False, regardless of what the model returned.
- CLI (`generate.py` argparse, `plan` subcommand): add `--dates` (`store_true`, default `False`). Wire into `main()`'s `do_plan(...)` call.
- `dashboard/fileops.py`:
  - `_plan_args(profile_slug, params)` — append `--dates` when `params.get("dates")` is truthy.
  - `run_plan` unchanged otherwise (params dict already flows straight from the POST body).
- `dashboard/osctl.py` `generate-plan` subcommand — add `--dates` (`store_true`), forwarded into `params["dates"]` only when set (mirrors existing optional-param pattern in `_generate_plan`).
- `dashboard/app.js` `renderGenerateIdeas` — add a checkbox field "Assign dates to posts" under Period end, default unchecked. Period start/end stay required (still drive the filename and recent-history window even when no per-post dates are assigned). Include `dates: data.dates === "on"` (or equivalent checkbox read) in the POST payload only when checked.

Not in scope: persisting the checkbox's last value per profile — it resets to unchecked every time the Generate Ideas form opens.

### 2. Publish gate

- `dashboard/fileops.py` `set_status(post_id, new_status, profile_slug=None)` — before the existing transition-table check succeeds and writes, add: when `new_status == "published"` and `not ctx["post"].get("date")`, raise `ActionError("cannot publish '<id>' — add a date first")`. This sits alongside the existing `ALLOWED_TRANSITIONS` check so both the dashboard and any CLI/chat path that calls `set_status` are covered.
- No change to any other transition — `planned → approved_slot`, `approved_slot → briefed`, `briefed → approved` (Write it →, Review →) all work with no date, per the requirement that writing/reviewing stay unblocked.
- `dashboard/app.js` `renderProfile`'s `drawList()` — the `NEXT` map's `approved` entry (`{label:"Publish →", to:"published"}`) is looked up per-post at render time; when `p.status === "approved" && !p.date`, render the action button as `{label:"Add date to publish"}` that navigates to `#/post/${id}/edit` instead of calling `doNext`. Same rendering rule applies wherever `NEXT` drives a button for a post list (the Unscheduled bucket in §4 reuses this).

### 3. Clearing a date

- `dashboard/fileops.py` `update_post(post_id, fields, profile_slug=None)` — already pops `date` when `fields["date"]` is empty/whitespace via the generic `_POST_FIELDS` loop. Add a guard at the top of that loop (or specifically for `"date"`): if `"date" in fields` and `ctx["post"].get("status") == "published"`, raise `ActionError("cannot change the date of a published post")`. This blocks both clearing and re-dating a published post through the one write path every caller (dashboard edit form, chat `update-post`) already goes through.
- `dashboard/app.js` `renderEditPost` (post-edit form, ~line 1665 `finput("date", slot.date||"", 'type="date"')`) — add a "Clear date" button next to the date input, calling the same save handler with `date: ""`. Disable/hide the button (and make the date input read-only) when `slot.status === "published"`.

### 4. Unscheduled bucket (new nav view)

- Sidebar nav (`dashboard/app.js` `renderRail`, ~line 402-405): add `<a data-view="unscheduled"><span class="ico">◷</span> Unscheduled</a>` next to Needs you / Calendar / Operations.
- `ROUTES`: add `[/^\/unscheduled$/, () => { setState("unscheduled"); renderUnscheduled(); }]`.
- `refreshViews()`: add `if (v === "unscheduled") return renderUnscheduled();` alongside the existing view branches, so chat-triggered mutations refresh this view too.
- `renderUnscheduled()` — new function, no new API endpoint: `_POSTS` (loaded fresh on every `renderRail()` call via `/api/posts-index`, which `refreshViews`/initial load already call before rendering the active view) is filtered client-side to `p.status !== "published" && !p.date`. Group by `p.profile_name || p.profile_slug`; within each group, same filter chips as `renderProfile` (All / Ideas / Drafts — no Published chip, since published posts can't appear here). Row rendering, status pill, and the `NEXT` action button reuse the same logic as `renderProfile`'s `drawList()` (including the §2 "Add date to publish" override), parameterized by each row's own `profile_slug` for navigation (`#/post/${id}` needs `{profileSlug: p.profile_slug}` in nav extras, same as the profile page passes today).
- Page header shows a count ("N posts with no date") mirroring the profile page's "N posts" line.

Not in scope: bulk "assign dates to several posts at once" action in this view — each post is opened individually to add a date (existing edit form). Addable later without changing this design's shape.

## Data flow summary

```
Generate Ideas form (dates unchecked, default)
  -> POST /api/profile/<slug>/plan {period, ..., dates: false}
  -> fileops.run_plan -> generate.py plan --dates omitted
  -> do_plan(assign_dates=False) -> plan.txt tells model to omit date
  -> post-loop strips any date anyway -> plan-*.json posts have no "date" key

Sidebar "Unscheduled"
  -> renderUnscheduled() filters already-loaded _POSTS (status != published && !date)
  -> click a post -> existing #/post/:id or #/post/:id/edit routes

Publish attempt on an undated post
  -> UI: button reads "Add date to publish", routes to edit (no status call fired)
  -> API safety net regardless of caller: fileops.set_status raises before transition
```

## Testing

- `tests/test_generate_revise.py` or a new `tests/test_generate_plan.py` — `do_plan` with `assign_dates=False` (default) produces posts with no `date` key even when the model output includes one (mock `run_job` to return a plan with dates, assert stripped); `assign_dates=True` preserves the model's dates.
- `tests/test_fileops_posts.py` — transition to `published` without a date raises `ActionError`; with a date succeeds; transitions to non-published statuses succeed regardless of date.
- `tests/test_fileops_posts.py` — `update_post` clearing `date` on a non-published post succeeds; on a published post raises `ActionError`.
- No dashboard JS test suite exists in this repo (`app.js` is untested by convention here) — the Unscheduled view and button-label changes are verified manually per the "test UI changes in a browser" project convention.
