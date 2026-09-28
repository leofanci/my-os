# CRUD parity for memos, experiments, features

## Problem

Dashboard tabs render memos, experiments, and roadmap features as read-only
cards. Only `create` exists for any of them (`create-memo`, `create-experiment`,
`add-feature`); nothing lets a user edit or delete one, in the dashboard or in
chat. Every other artifact type with a card (posts, milestones, projects,
brief-specs, voices) already has edit + delete. This closes the gap so the
three remaining types match: same osctl-only write path, same UI pattern
(✎ edit / 🗑 delete on the card), available both manually and via chat.

Intake and technical subsections keep their current edit-only behavior
(no delete) — they're doc headings, not discrete records, and adding
delete there is a different, structural change. Out of scope here.

## Scope

**In scope**: edit + delete for memos, experiments, roadmap features.
Validation tab intake wired to the same editable-subsection mechanism the
Technical tab already uses (edit only, no delete — parity with Technical).

**Out of scope**: deleting individual subsection headings, bulk delete,
memo version history browsing/rollback, editing experiment `status`/
`decision`/`result` (those aren't part of the manual-edit field set today —
`EXPERIMENT_FIELD_SPECS` covers only `assumption`, `success_criteria`,
`kill_criteria`, matching the existing New Experiment form).

## Data model notes

- **Memos** are versioned JSON files: `strategy/<type>-v<N>.json`. `edit`
  means patching the *specific version's* file in place (the version shown
  on the card), not creating v(N+1). `delete` removes that version file. No
  change to the versioning scheme itself — `create-memo` still always
  creates the next version.
- **Experiments** are `strategy/experiments/<stem>.json`. `update_experiment`
  already exists in `fileops.py` and patches `assumption`, `success_criteria`,
  `kill_criteria`, `status`; only `delete` and the HTTP/UI wiring are missing.
- **Features** live as checklist lines inside `products/<slug>/roadmap.md`:
  `- [ ] Title — why — priority: X` under a `## Section` heading. There is no
  per-feature file — `update_feature`/`delete_feature` find the line by
  matching `slug_key(title)` against the feature's id (same matching
  `add_feature` uses to mint the id) and rewrite/remove just that line,
  same regex-substitution approach `delete_activity` already uses for its
  checklist lines.

## Backend changes

`dashboard/fileops.py` — new functions, following existing sibling patterns:

- `update_memo(project_slug, memo_type, version, fields)` — loads
  `<type>-v<version>.json`, patches allowed fields (same field set
  `create_memo` accepts for that type), re-normalizes, writes back in place,
  reindexes. 404s via `ActionError` if the version file doesn't exist.
- `delete_memo(project_slug, memo_type, version)` — deletes the version file,
  reindexes. `ActionError` if missing.
- `delete_experiment(project_slug, stem)` — deletes
  `strategy/experiments/<stem>.json`, reindexes.
- `update_feature(product_slug, feature_id, fields)` — locates the checklist
  line whose `slug_key(title)` matches `feature_id`, rewrites title/why/
  priority in place; if `section` changed, moves the line to the target
  `## Section` block (reusing `_roadmap_section_name` for validation).
  Preserves the checkbox state (`[ ]`/`[x]`).
- `delete_feature(product_slug, feature_id)` — removes the matching line via
  regex substitution (pattern mirrors `delete_activity`), reindexes.

Note: a feature's composed id is derived from `slug_key(title)` (same as
`add_feature` mints it today), so renaming a feature via `update_feature`
changes its id. This is existing behavior, not new — no feature id is
persisted elsewhere in the codebase for this to break.

`dashboard/osctl.py` — new subcommands, same argparse shape as their
existing siblings (`update-experiment`, `create-memo`, `add-feature`):

- `update-memo --project <slug> --type <type> --version <N> [--summary] [--recommendation] [--problem-statement] [--body-json ...]`
- `delete-memo --project <slug> --type <type> --version <N>`
- `delete-experiment --project <slug> --stem <stem>`
- `update-feature --product <slug> --id <feature-id> [--title] [--why] [--section] [--priority]`
- `delete-feature --product <slug> --id <feature-id>`

## HTTP routes (`dashboard/server.py`)

Extend the generic table-driven dispatch already used for brief-specs/voices
(`_ARTIFACT_ROUTES`) with a parallel table for project-scoped artifacts,
mounted under `/api/project/<slug>/memo/<type>/<version>/...` and
`/api/project/<slug>/experiment/<stem>/...`, plus
`/api/product/<slug>/feature/<id>/...` for features — `update` and `delete`
verbs per entry, matching the `.../update` / `.../delete` suffix convention
the existing table uses. No new dispatch *shape*, just new table rows plus
the two extra id segments memos need (type + version) that brief-specs/
voices don't.

## Dashboard UI (`dashboard/app.js`)

- `renderMemoCard`, `renderExperimentCard`, `renderFeatureCard` each grow
  ✎ / 🗑 buttons in their card head, same visual pattern as `rail-edit`
  (`data-edit-memo`, `data-del-memo`, etc.).
- Edit opens the *same form* already used for "New Memo" / "New Experiment" /
  "New Feature" (`schemaFields(...)`-driven), prefilled from the card's
  current values, posting to the new `update` route instead of `create`.
- Delete reuses the existing `renderConfirmDelete` modal flow (same one
  posts/milestones already use) — no new confirmation UI.
- Validation tab: swap the intake `renderFileCard` call for
  `renderMdSubsections(..., { editable: true })`, identical to how
  `renderTechnicalSection` already renders `technical.md`. No delete button
  added here — matches Technical tab's existing edit-only behavior.

## Chat parity

Free by construction: the chat agent's Bash tool is restricted to
`python -m dashboard.osctl:*` with no per-command allowlist, so the five new
subcommands are callable the moment they exist — no per-skill prompt changes
required. Add the five new commands to the mandatory osctl table in the root
`CLAUDE.md` (the one skills and the chat agent read) so they're documented
turn-of-crank alongside the existing `update-experiment`/`create-memo`/
`add-feature` rows, and add `update-memo`/`delete-memo`/`delete-experiment`/
`update-feature`/`delete-feature` to the "banned" note's *complement* — i.e.
these join the sanctioned mutation path, nothing is un-banned.

## Testing

Match existing coverage shape (`tests/test_fileops_crud.py`,
`tests/test_server_*`): one fileops unit test per new function (happy path +
not-found `ActionError`), one server HTTP-route test per new endpoint, and an
osctl CLI smoke test per new subcommand, following the patterns already used
for `update_experiment`/`delete_activity`/`delete_milestone`. UI wiring
verified manually in-browser (per project convention — no JS test harness in
this repo).
