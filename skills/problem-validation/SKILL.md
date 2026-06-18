---
name: problem-validation
description: Validate that a problem is real, painful, and frequent BEFORE any GTM or build work - for a project (full memo) or any activity/idea (quick gut-check). Use when the user has an idea, says "is this worth doing", "do people actually need this", or before running gtm-assessment.
---

# Problem Validation (runs first, across activities)

The front of the loop. Before positioning, channels, or building anything,
establish that the problem is real. This is where evidence-driven discipline
matters most — most ideas die here and should.

Runs at two depths:
- **Full** (a project): read `projects/<project-slug>/strategy/intake.md` + evidence log, write a memo.
- **Quick** (any activity/idea, GTM or not): a lightweight gut-check, no memo —
  can graduate into a full validation if it survives.

## Full mode → `projects/<project-slug>/strategy/memos/problem-validation-vN.json`
```json
{
  "version": 1, "date": "",
  "problem_statement": "the problem in the CUSTOMER'S words, not the solution",
  "who_has_it": "specific segment, not 'everyone'",
  "severity": "vitamin | painkiller | emergency",
  "frequency": "how often they hit it (daily/weekly/rare)",
  "current_workaround": "what they do today — spreadsheet, competitor, nothing",
  "evidence": [{"signal":"what was observed","source":"interview|data|sales|none","strength":"weak|moderate|strong"}],
  "willingness_to_pay_signal": "any sign money/time follows the pain — or 'none yet'",
  "validation_status": "unvalidated | weak | strong",
  "cheapest_next_test": "the single fastest way to move status up (usually problem interviews or a demand probe)",
  "recommendation": "proceed_to_gtm | keep_validating | drop — and why",
  "superseded_memo": null
}
```

## Quick mode (activity/idea, conversational — no file)
Four questions only: Who exactly has this? How badly / how often? What do they
do today instead? What's the cheapest way to find out if it's real this week?
End with: proceed / validate first / drop — and why. If it's worth a real
project, recommend running `venture-intake` then full problem-validation.

## Rules
- A problem is not validated because it's validated in your head. "I'd use this"
  ≠ evidence. If the only evidence is the founder's belief, status = "unvalidated".
- Distinguish a *painkiller* (they already pay/work around it) from a *vitamin*
  (nice-to-have) — vitamins rarely justify GTM spend; say so plainly.
- `validation_status` GATES the pace call: gtm-assessment must NOT recommend
  "accelerate" while problem validation is "unvalidated" or "weak".
- The cheapest next test feeds experiment-design; results feed the intake
  evidence log and bump this memo's version.
- Never fabricate evidence strength. No evidence = "weak"/"unvalidated", said openly.
