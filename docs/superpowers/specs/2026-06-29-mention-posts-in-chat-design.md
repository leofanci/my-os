# @-mention posts by id in chat — design

**Date:** 2026-06-29
**Scope:** Make each post @-referenceable in the dashboard chat by its post id (e.g. `@post-001`), like profiles/channels already are.

## Problem

Chat @-mention candidates come from `_TREE` (`/api/tree`): project → profile → channel only. Posts are not mentionable. User wants to pull a specific post into chat context by its id.

Not in scope: metadata tag field on posts, filtering content by tag, controlled vocab. This is chat referencing only.

## Current behavior (what already exists)

- `app.js:1184` — @-mention autocomplete. `mentionCandidates()` walks `_TREE`, builds `@slug` tokens, tracks picks in `mentions[]`.
- `buildContext(text)` (`app.js:1315`) — on send, resolves surviving `@`-tokens into a "Referenced entities" block (type/name/slug, identity only), and separately inlines the **currently-open post** (`CURRENT_POST`) as full slot+brief JSON.
- Chat backend (`chat_session.py`): lean Sonnet subprocess, Bash→osctl only.

## Design

### 1. Post candidates
Posts aren't in `_TREE` and shouldn't bloat it. Add a flat index:
- New endpoint `GET /api/posts-index` → `[{id, title, pillar, stage, profile_slug, profile_name}]` across **all** profiles.
- Client fetches once on chat init, caches beside `_TREE`.
- `mentionCandidates()` appends posts: `type:"post"`, `slug:id`, token `@<id>`, label = `working_title || pillar || id`, meta = `profile_name · stage`.
- Menu icon for posts (e.g. `✎`); existing `ICON` map gains a `post` key.

### 2. Resolution (inline full content)
When a `@post-xxx` token survives in the sent message, `buildContext` inlines that post's full slot+brief JSON — same shape `CURRENT_POST` already uses — so chat reads caption/slides directly with no osctl round-trip.
- `buildContext` becomes async (fetch `/api/post/{id}` per referenced post). `send` already `await`s it.
- **Cap:** inline full content for up to 5 referenced posts; beyond that, include id + title only.
- The post currently open via `CURRENT_POST` stays as-is; if it's also @-referenced, dedupe by id.

## Decisions

- **All posts** in the index, not just current-profile scoped — `@post-001` works from any view; filter-as-you-type handles list size.
- **Inline full content** over id-only — consistent with `CURRENT_POST`, lean chat reads without extra tool call, posts are small.
- **Cap at 5** full inlines to protect context.

## Affected files

- `dashboard/server.py` — add `/api/posts-index` route.
- `dashboard/fileops.py` (or wherever post listing lives) — flat post index helper.
- `dashboard/app.js` — fetch + cache index, extend `mentionCandidates()`/`ICON`, make `buildContext` async with post inlining + cap.

## Tests

- index helper returns all posts with required fields across profiles.
- `buildContext` inlines referenced post JSON; respects cap; dedupes with `CURRENT_POST`.
