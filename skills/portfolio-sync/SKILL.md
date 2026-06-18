---
name: portfolio-sync
description: Given the current unified timeline, surface this week's coordination actions across entities - what to align, what to sequence, what's blocking what. Use for "what needs syncing", "are my profiles aligned with my launches", or before weekly review.
---

# Portfolio Sync

Query `os.db` (the `timeline` VIEW + `entities`) for this week's window; fall
back to `portfolio/timeline-<latest>.json` and reading the projects folder
structure if the index is missing. Not what to plan — what to DO THIS WEEK
because of how entities interact (projects, profiles, products, and channels).

## Output: coordination memo (conversational, not JSON)

### 1. Cross-entity alignments needed this week
For each project + its linked profile(s), and each profile + its linked product(s):

- Is the profile's content this week aligned with the project's current phase?
  (experimenting = community/learning tone; pre-launch = warm-up/teasing;
  post-launch = social proof/conversion)
- If a launch is within 3 weeks: is a content ramp planned? If not, flag it.
- If a product has a release this week: does profile content reflect or support it?
- If two profiles share the same product or landing page: are they sending
  conflicting messages?

### 2. Sequencing decisions
Things that are out of order or unsequenced. State:
- What should happen before what
- Which entity it affects
- The risk if the order is wrong
  Example: "Launch plan for Project A exists but ICP is still unvalidated —
  the launch targeting is built on an assumption. Lock ICP before finalizing launch."

### 3. This week's cross-portfolio actions (max 5)
Only things requiring coordination BETWEEN entities. Per action:
- What to do
- Which entities it touches
- Which skill to run
- Why this week (what breaks if deferred)

### 4. What to defer explicitly
1-2 things that look urgent but can wait — and why.
This prevents "everything is priority" paralysis.

## Rules
- Draw from BOTH the timeline and the resource_note.
  A coordination action that requires 8h in a 5h/week project is not an action —
  it's a resourcing problem. Name it as such.
- Distinguish conflict (two things that clash) from sequencing (one before another).
  They need different fixes.
- End with: "Want to start with [top priority]?" and route to the right skill.
