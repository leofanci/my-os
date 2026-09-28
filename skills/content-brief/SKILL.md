---
name: content-brief
description: Create or update post briefs, revise draft/slot copy, edit brief-spec, and add slide rows — all via osctl. Use when the user edits a post idea, changes hooks/slides/draft text, says "revise this post", "update the brief", "generate a brief", "brief spec", or tweaks what a post should say. Not content calendars (content-plan) or cross-channel repurposing (copy-variants).
---

# Content Brief

Writes: `dashboard/ai_rules.py`. Do not author JSON yourself.

## When to use this (not copy-variants or content-plan)
- **content-brief**: one post — brief fields, draft/slot copy, slide overlays, profile brief-spec rules.
- **copy-variants**: adapt one piece across channels/platforms or generate hook variants for testing.
- **content-plan**: calendar skeleton for a date range (`generate-plan`).

## Route by intent
| User says | Command |
|---|---|
| Change profile output rules / brief-spec | `get-brief-spec` → minimal edit → `update-brief-spec` |
| New post direction, or change what the post is about | `update-brief --id <post-id> --instruction "<their words>"` |
| Auto-generate brief (Write button path) | `generate-brief --id <post-id>` |
| Revise draft, slot, hook, slides, overlay text | `revise-post --id <post-id> --instruction "<their words>"` |
| Append one slide row (explicit overlay text) | `add-slide --id <post-id> --overlay "<text>"` |

`update-brief` on an existing brief routes to revise internally — either command works. Prefer `revise-post` when the user names copy/draft/slides/hooks and does not say "brief". Prefer `update-brief` when they are shaping or reshaping the post idea.

## This turn
1. Brief-spec change? → `get-brief-spec`, apply user intent, `update-brief-spec` (full file).
2. Post idea or brief change? → `update-brief --id <post-id> --instruction "<their words>"` (or `generate-brief` if they want auto).
3. Draft/slot/slide/hook copy change? → `revise-post --id <post-id> --instruction "<their words>"` (or `add-slide` for a single new overlay row).
4. One-sentence confirmation — never paste brief/spec/draft back.