---
name: content-plan
description: Generate a content calendar skeleton for a profile - dated slots with channel targets, pillar, objective, and concept (no full copy yet). Use for "plan next two weeks of content" or recurring planning.
---

# Content Plan (calendar skeleton)

Read the VOICE CASCADE for the profile (project.md + profile.md + channel
guidelines for targeted channels) + last ~20 planned/approved slots (avoid repetition).
Ask only for: period, platforms/channels, cadence, optional focus.

Voice cascade: `projects/<project-slug>/project.md` (project voice)
             + `projects/<project-slug>/profiles/<profile-slug>/profile.md` (profile voice)
             + `profiles/<profile-slug>/channels/<channel-slug>/guidelines.md` (per-channel rules)

## Output: `projects/<project-slug>/profiles/<profile-slug>/content/plan-<period>.json`
```json
{"period":"","profile":"<profile-slug>","strategy_note":"the angle for this period and why",
 "posts":[{"id":"draft-001","date":"","channels":["<channel-slug>"],"platform":"",
   "pillar":"",
   "objective":"awareness|engagement|conversion|community|authority",
   "working_title":"","concept":"2-3 sentences: what this post does and why now"}]}
```

## Rules
- Pillar mix must respect profile.md percentages; objectives must match the
  channel-goals table.
- Respect the promo frequency cap from the profile voice.
- Skeleton only — no captions/hooks yet. The user approves/edits/kills slots,
  THEN content-brief expands approved ones. Never expand unapproved slots.
- Each post targets one or more channels (by channel slug).
- Honor channel guidelines for each targeted channel.
- Summarize the calendar as a readable table, not raw JSON.
