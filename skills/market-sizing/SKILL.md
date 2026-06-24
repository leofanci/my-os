---
name: market-sizing
description: Estimate SAM and SOM for a project using a bottom-up approach anchored to real buyer counts, not top-down TAM percentages. Use before GTM investment decisions, when the user asks "how big is this", or after ICP research has identified a beachhead segment.
---

# Market Sizing

Read `projects/<project-slug>/strategy/intake.md` + ICP memo if present +
competitor memo if present.

Bottom-up only. Never start from "X% of a $Y billion market" — that tells you
nothing actionable. Start from countable buyers.

## Method

**SAM (Serviceable Addressable Market)**
Count the real population you could serve given your actual model and reach:
1. Identify the specific segment (from ICP memo or intake) — narrow beats vague.
2. Find a countable proxy: LinkedIn filter results, community size, job postings,
   known customer counts of direct competitors, niche publication subscriber counts.
   State the source and its reliability (exact / estimated / rough guess).
3. Apply a realistic reach filter: what fraction of that pool you could actually
   get in front of given distribution constraints (no brand, no sales team, no ad
   budget if that's the reality). Be conservative.
4. Multiply by ARPU (use pricing memo if available; otherwise use a range).
5. Express as annual revenue potential with low/mid/high assumptions shown.

**SOM (Serviceable Obtainable Market) — the number that matters**
What you could realistically capture in 12–18 months:
1. Start from SAM, not from the sky.
2. Apply an honest capture rate for the stage: 0.5–3% is typical for a solo/small
   team with no paid acquisition in year one — state the assumption explicitly.
3. State what would need to be true for the number to be bigger (funding, partnership,
   viral loop, etc.) — don't bake in assumptions you don't have a plan for.
4. Convert to: # customers, MRR, ARR. Both revenue and customer count.

## Output
```json
{
  "version": 1, "date": "",
  "segment": "the specific buyer population sized",
  "sam": {
    "population": "N buyers — source + reliability",
    "reach_filter": "why only X% are reachable for this project",
    "arpu_assumption": "$/year — source (pricing memo / competitor / assumption)",
    "annual_revenue_low": 0,
    "annual_revenue_mid": 0,
    "annual_revenue_high": 0
  },
  "som": {
    "capture_rate": "X% — stated assumption",
    "customers_year1": 0,
    "mrr_year1": 0,
    "arr_year1": 0,
    "what_changes_the_number": "the 1-2 assumptions that move this 5x"
  },
  "sizing_confidence": "low | medium | high",
  "recommendation": "is this worth GTM investment at this stage — and why"
}
```

Rules:
- If you can't find a countable proxy, say so and explain what research would find one
  (don't fabricate population numbers).
- Sizing confidence = high only if population source is verified data; most early-stage
  estimates are "low" or "medium" — say it openly.
- A small SOM isn't a kill signal — a $500K ARR SOM with real evidence beats a
  $50M SOM built on assumptions. Frame accordingly.
- This feeds gtm-assessment and launch-plan; a SOM too small to justify GTM spend
  should be flagged directly.

Save to `projects/<project-slug>/strategy/memos/market-sizing-vN.json`.
