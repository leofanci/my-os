---
name: experiment-design
description: Design the cheapest test for a project's riskiest assumption, with success and kill criteria. Use when the user asks what to test, how to validate, or whether to talk to users before launching.
---

# Experiment Design (Job C)

Read `projects/<project-slug>/strategy/intake.md` + latest assessment.
Target the TOP riskiest assumption unless the user names another.

## Output: 2-3 experiment options, then one recommendation
```json
{"assumption_under_test":"",
 "experiment_options":[{
   "name":"e.g., 10 problem interviews | landing-page smoke test | concierge MVP | fake-door | presale",
   "design":"exact steps, who to recruit, what to say/build",
   "cost":"time + money", "duration":"calendar time",
   "success_criteria":"quantified: 'X of Y do Z'",
   "kill_criteria":"result that means stop/pivot",
   "pros":[], "cons":[]}],
 "recommendation":""}
```

## Rules
- Cheapest test that produces a real signal wins. If interviews answer it, don't build.
- Success criteria set BEFORE running — no moving goalposts. Kill criteria mandatory.
- Design must fit intake resources (hrs/week, budget). A 40h test for a 5h/week
  project is invalid.
- Save to `projects/<project-slug>/strategy/experiments/exp-NNN-design.json`.
  Tell the user to come back with results → experiment-review.
