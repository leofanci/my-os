---
name: content-plan
description: Generate a content calendar skeleton for a profile via the generate.py pipeline. Use for "plan next two weeks of content" or recurring planning.
---

# Content Plan (calendar skeleton)

Same job as dashboard **Generate ideas** button. Do not author plan JSON yourself.

## Write gate (same as posts)
1. **Propose** — period, cadence, focus in chat. Target profile Posts (`pfN.sec00`). No osctl.
2. **Review** — user confirms period/platforms.
3. **Commit** — `generate-plan` creates `planned` slots for user to review in Posts UI.

```bash
python3 -m dashboard.osctl generate-plan --profile <profile-slug> \
  --period "YYYY-MM-DD to YYYY-MM-DD" \
  [--platforms tiktok,instagram] [--cadence 3] [--focus "push the launch"]
```

Skeleton only — no captions yet. After user approves slots in UI: `generate-brief` per post.
Summarize with `get-posts`, not raw JSON.