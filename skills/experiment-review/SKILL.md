---
name: experiment-review
description: Log experiment results, judge them against pre-set criteria, and decide persist/pivot/kill. Use when the user reports back what happened in a test, interviews, or launch.
---

# Experiment Review

1. Read the experiment's design file from `projects/<project-slug>/strategy/experiments/`
   (its success/kill criteria are the contract).
2. Take the user's raw results; push for numbers over impressions.
3. Verdict against the PRE-SET criteria: met / failed / inconclusive.
   - Do not let enthusiasm or sunk cost reinterpret the criteria afterward.
4. Decision memo: persist (scale what worked) / pivot (what specifically changes)
   / kill (and what's salvageable) — with pros/cons if genuinely ambiguous.
5. Write results into `projects/<project-slug>/strategy/experiments/exp-NNN-result.json`
   AND append a dated entry to `projects/<project-slug>/strategy/intake.md`'s Evidence log.
6. If the result changes the strategic picture, recommend rerunning gtm-assessment.

## Honesty rules
- "Inconclusive" is a valid verdict; recommend a sharper follow-up test.
- 3 polite friends saying "cool idea" = zero evidence. Say so kindly.
