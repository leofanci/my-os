---
name: content-brief
description: Expand approved calendar slots into full post briefs - hook, structure, caption, CTA, hashtags, visual brief with a genai prompt draft. Use after slots are approved or when the user asks to draft specific posts.
---

# Content Brief (full post)

Read the VOICE CASCADE for the profile (project.md + profile.md + channel
guidelines) + the approved slot(s). One brief per slot.

Voice cascade: `projects/<project-slug>/project.md` (project voice)
             + `projects/<project-slug>/profiles/<profile-slug>/profile.md` (profile voice)
             + `profiles/<profile-slug>/channels/<channel-slug>/guidelines.md` (per-channel rules)

```json
{"id":"","channels":["<channel-slug>"],"platform":"",
 "format":"reel|carousel|single_image|text|thread|short|story",
 "objective":"","pillar":"",
 "hook":"first line / first 2 seconds — the scroll-stopper",
 "structure":["beat 1","beat 2","beat 3"],
 "caption":"ready-to-post text",
 "cta":"exact line — MUST be from profile.md allowed CTAs",
 "hashtags":[],
 "visual_brief":{"description":"scene by scene if video","mood":"from profile voice",
   "format_specs":"9:16 ~30s | 4:5 carousel 5 slides | …",
   "text_overlays":[],
   "genai_prompt_draft":"first-pass prompt for a future image/video gen tool"},
 "notes_for_human":"flags: needs fact-check, needs real photo, etc."}
```

## Rules
- Hook gets the most effort: offer 2-3 hook options when the post matters.
- Caption respects channel guidelines and platform char limits; voice checked
  against "we never sound like" from the profile voice.
- visual_brief.genai_prompt_draft must be self-contained (usable without
  reading the rest) — it's the future hook for image/video generation tools.
- Save to `projects/<project-slug>/profiles/<profile-slug>/content/briefs/`;
  present briefs readably.
