---
name: venture-intake
description: Create or update a project's strategy/intake.md through a structured interview. Use when the user mentions a new startup/project (kind=venture), or when new evidence (experiment results, sales, interviews) should be logged.
---

# Venture Intake

Goal: produce/update `projects/<project-slug>/strategy/intake.md`.
Honest answers > impressive answers.

## Process
1. If `projects/<project-slug>/project.md` doesn't exist, scaffold it first
   (or offer to run portfolio-map).
2. If strategy/intake.md exists, read it and only ask about gaps or changes.
3. Interview conversationally, max 3 questions at a time, covering:
   - What it is: one-liner, problem in customer's words, current alternative, why now
   - Stage & evidence: idea/prototype/live/revenue; concrete numbers (even zero);
     strongest validated assumption; riskiest UNvalidated assumption
   - Market: best-guess ICP, who pays vs. uses, market type, geography, price point
   - Resources: hrs/week, test budget, team, unfair advantages, hard constraints
   - Goals: 6-month success definition, risk appetite, user's own kill criteria
   - Portfolio: priority vs. other projects
4. Push back on vague answers ("growing fast" → "how many, since when?").
5. Write intake.md with an `## Evidence log` section at the bottom — every
   experiment-review appends dated entries there.
6. If material facts changed, recommend rerunning gtm-assessment.
