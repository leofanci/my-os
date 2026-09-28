---
name: brand-identity
description: Create or refresh a profile voice (voices/vc{N}.md) and/or channel guidelines through interview or from a channel-strategy mandate. Use for new profiles, "define my profile voice", or when content output feels off-brand.
---

# Profile Voice & Channel Guidelines

Goal: produce `projects/<project-slug>/profiles/<profile-slug>/voices/vc1.md` (the
default voice — a profile can have more than one, see below) via `create-voice`/
`update-voice --profile <slug> [--id vcN] --text "..."`. Never write voices/*.md
by hand. Quality here determines all content quality downstream.

Distinctiveness beats differentiation. The strongest evidence on brand growth
(Byron Sharp, *How Brands Grow*, drawing on Ehrenberg-Bass Institute research)
is that consistent, recognizable distinctive assets — a repeated color, shape,
phrase, visual device, sound — drive recognition and mental availability more
reliably than "authentic" tone or differentiated messaging, which most audiences
don't actually perceive as differentiated. Push for a distinctive asset (section
6 below) before polishing voice adjectives; a profile people instantly recognize
beats one that merely "sounds right."

VOICE CASCADE: project voice (project.md body) → profile voice (voices/vc{N}.md,
default vc1) → channel guidelines (channels/<channel-slug>/guidelines.md)

A profile can have several voices (vc1, vc2, ...), each tagged `platforms:`
(`all` or a comma list) for the human's reference — selection between them is
always manual, never auto-matched. Default this skill to vc1 unless the user
asks for a second, platform-specific voice, in which case use `create-voice`
(mints the next id, no --id flag) instead of overwriting vc1.

## Two entry paths
- **From a project**: read the channel-strategy memo's social_media_mandate.brand_brief_seed
  + the project's strategy/intake.md; pre-fill the file, interview only for gaps.
  Add `project: <project-slug>` frontmatter.
- **Standalone profile**: full interview, max 3 questions at a time.

## File sections (keep total under ~1,500 words)
1. Core: name, one-line positioning, mission, niche, stage
2. Audience: primary/secondary, pain points, aspirations, where they hang out
3. Voice & tone: 3 adjectives, "we sound like", "we never sound like",
   vocabulary do/don't, emoji policy, humor
4. Content pillars: 3-5, each with description + % of calendar
5. Goals per channel: table of channel → primary goal → format bias
6. Visual identity: palette, mood, imagery style, always/never include — this is
   the distinctive-asset section; push for ONE consistently repeated device
   (not just a palette) people would recognize with the logo covered
7. CTAs & conversion: allowed CTAs, destination, promo frequency cap
8. Hard rules: never mention/do, compliance
9. References: 3 posts that nailed it, admired accounts, accounts NOT to resemble

## Channel guidelines (per channel, optional but recommended)
After writing the voice, offer to draft `channels/<channel-slug>/guidelines.md`
for each channel this profile uses. Each guidelines.md has a `## General` section
(cross-channel rules) and one `## <Platform>` section per platform covered.

## File locations
- `projects/<project-slug>/profiles/<profile-slug>/voices/vc1.md` (via `create-voice`/`update-voice`, not written by hand)
- `projects/<project-slug>/profiles/<profile-slug>/channels/<channel-slug>/guidelines.md`

## Rules
- Push past generic answers ("authentic and fun" describes everyone — ask for a
  named person/archetype the profile sounds like).
- Offer drafts to react to rather than blank questions when the user is stuck.
- On refresh: show a diff of what changed and why.
- Prioritize the distinctive-asset work (section 6) over tone wordsmithing when
  time is limited — recognition compounds, clever phrasing rarely does.
