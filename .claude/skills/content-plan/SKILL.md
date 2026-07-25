---
name: content-plan
description: Generate a content calendar skeleton for a profile via the generate.py pipeline. Use for "plan next two weeks of content" or recurring planning.
---

# Content Plan (calendar skeleton)

Same job as dashboard **Generate ideas** button. Do not author plan JSON yourself.

## Cadence guidance
Default to at least 3x/week per platform when the user states no preference —
below that, feeds don't get enough signal to learn the audience and followers
don't form a checking habit. This is directional practitioner guidance (TikTok
Creator Portal, Meta Blueprint consistency guidance; also the sustained-vs-burst
activity findings in Les Binet & Peter Field, *The Long and the Short of It*),
not a measured constant — treat it as a floor, not a target. Check it against
the profile's real hrs/week from intake and say so if the requested cadence is
unsustainable.

## Write gate (same as posts)
1. **Propose** — period, cadence, focus in chat. Target profile Posts (`pfN.sec00`). No osctl.
2. **Review** — user confirms period/platforms.
3. **Commit** — `generate-plan` creates `planned` slots for user to review in Posts UI.

```bash
python3 -m dashboard.osctl generate-plan --profile <profile-slug> \
  --period "YYYY-MM-DD to YYYY-MM-DD" \
  [--platforms tiktok,instagram] [--cadence 3] [--focus "push the launch"] [--dates]
```

Unscheduled by default — posts land with no date, sorted into the Unscheduled
view. Only add `--dates` when the user explicitly asks for the batch to be
dated/scheduled now; do not add it just because the request sounds calendar-shaped.

Skeleton only — no captions yet. After user approves slots in UI: `generate-brief` per post.
Summarize with `get-posts`, not raw JSON.