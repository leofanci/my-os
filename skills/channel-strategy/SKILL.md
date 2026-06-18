---
name: channel-strategy
description: Compare go-to-market channels and entry strategies for a project and recommend a primary channel. Use after an approved GTM assessment, or when the user asks "where should I find customers" or "should I do social/outreach/paid".
---

# Channel & Entry Strategy (Job B)

Requires: `projects/<project-slug>/strategy/intake.md` + an approved gtm-assessment
(read both). If no assessment exists, say so and offer to run it first.

## Evaluate channels against THIS project's ICP and resources
Candidates: social_organic, outreach, community, paid, partnerships, content_seo,
product_led, events/offline. For each plausible one:
```json
{"channel":"","fit_reasoning":"","pros":[],"cons":[],
 "cost":"time+money","time_to_signal":"","verdict":"primary|secondary|not_now"}
```
Plus 2-3 entry_strategy_options (e.g., niche beachhead vs. broad launch) with
pros/cons, and one recommendation.

## Social media mandate (bridge to the profile layer)
Always include:
```json
{"needed": true, "purpose":"what social is FOR in this GTM (or why it's not needed)",
 "brand_brief_seed":"1 paragraph seeding a profile voice (brand-identity) run"}
```
Be willing to say social is NOT the right channel. Solo founder + B2B enterprise
ICP usually means outreach beats Instagram.

## Rules
- Time_to_signal matters as much as potential: prefer channels that produce
  learning in weeks, given the user runs a portfolio.
- Max ONE primary channel. Spreading a solo founder across 3 channels is a con, say it.
- Save to `projects/<project-slug>/strategy/memos/channels-vN.json`, summarize conversationally.
