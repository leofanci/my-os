---
name: tokensave
description: Inspect the active project's linked app through fresh, bounded TokenSave context supplied by myOS. Read-only and explicitly opt-in.
---

# TokenSave linked-app inspection

Use only for the active myOS project's linked local app. This is read-only.

1. Use the `Fresh TokenSave context` already included in this turn. myOS
   incrementally refreshed and queried the active app exactly once before the
   model started.
2. Use Glob/Grep and Read (maximum 200 relevant lines at a time) only when the
   supplied graph result is insufficient and those tools are available.
3. Summarize the answer; do not paste the entire graph response.

Never invoke TokenSave commands directly. myOS handles its bounded incremental
refresh outside the model turn. If the linked app has no index or refresh fails,
myOS stops `/tokensave` before starting the model and reports the problem.
