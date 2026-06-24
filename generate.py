#!/usr/bin/env python3
"""generate.py — synchronous claude -p content pipeline (Plan + Brief jobs).

Verified CLI pattern (Claude Code 2.1+): the profile voice file is CONTENT, so
it is piped as the user turn via stdin; the task + schema live in the prompt.
There is no --append flag.

    cat projects/<project>/profiles/<slug>/profile.md | \
        claude -p "$(cat prompts/plan.txt)" --output-format json

Jobs run synchronously (no jobs queue table — see BUILD.md Phase 1, Track A).
Output JSON is validated before writing; on a parse/validation error the job
retries ONCE with the error appended, then fails.

Hierarchy:
    projects/<project-slug>/
        project.md                  ← project voice (injected first)
        profiles/<profile-slug>/
            profile.md              ← profile voice (injected second)
            content/plan-<period>.json
            content/briefs/<post-id>.json
            channels/<channel-slug>/
                channel.md          ← per-channel notes
                guidelines.md       ← per-platform posting guidelines (injected)

Usage:
    python3 generate.py plan  <profile-slug> --period "2026-06-15 to 2026-06-28" \
        [--platforms instagram,x] [--cadence 3] [--focus "push the launch"]
    python3 generate.py brief <profile-slug> <post-id>
    python3 generate.py refine-guidelines <channel-slug>

Optional --workspace ROOT (default: cwd). Writes to:
    plan  -> projects/*/profiles/<profile-slug>/content/plan-<period>.json
    brief -> projects/*/profiles/<profile-slug>/content/briefs/<post-id>.json
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"

# Content jobs are bounded, schema-constrained generations — Sonnet does them
# well and is far faster/cheaper than the user's interactive default (which may
# be Opus at high effort). Pinning the model here is what keeps a 14-brief batch
# from taking ~15 minutes. Override with --model.
DEFAULT_MODEL = "sonnet"


class JobError(Exception):
    """A job that could not be completed (after the single retry)."""


# --------------------------------------------------------------------------- #
# claude invocation + output handling (split out so they're unit-testable)
# --------------------------------------------------------------------------- #
def run_claude(prompt: str, stdin_text: str, model: str = DEFAULT_MODEL) -> str:
    """Invoke `claude -p ... --output-format json`, return the raw stdout."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise JobError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout


def extract_result(stdout: str) -> str:
    """Pull the model's text out of the --output-format json envelope.

    The envelope looks like {"type":"result","subtype":"success","result":"...",...}.
    Falls back to the raw stdout if it isn't the expected envelope.
    """
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout
    if isinstance(env, dict):
        if env.get("is_error") or env.get("subtype") not in (None, "success"):
            raise JobError(f"claude reported an error: {env.get('subtype')}")
        if "result" in env:
            return env["result"]
    return stdout


def parse_model_json(text: str) -> dict:
    """Parse the model's reply as JSON, defensively stripping any code fences."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return json.loads(t)  # raises JSONDecodeError on failure


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_plan(obj) -> list:
    errs = []
    if not isinstance(obj, dict):
        return ["plan is not a JSON object"]
    for key in ("period", "profile", "posts"):
        if key not in obj:
            errs.append(f"missing top-level key '{key}'")
    posts = obj.get("posts")
    if not isinstance(posts, list) or not posts:
        errs.append("'posts' must be a non-empty array")
    else:
        for i, p in enumerate(posts):
            if not isinstance(p, dict):
                errs.append(f"posts[{i}] is not an object")
                continue
            for k in ("id", "date", "channels", "pillar"):
                if not p.get(k):
                    errs.append(f"posts[{i}] missing '{k}'")
    return errs


def validate_revise_idea(obj) -> list:
    errs = []
    if not isinstance(obj, dict):
        return ["revised slot is not a JSON object"]
    if not obj.get("id"):
        errs.append("missing 'id'")
    return errs


def validate_brief(obj, slot_id: str) -> list:
    if not isinstance(obj, dict):
        return ["brief is not a JSON object"]
    errs = []
    if obj.get("id") and obj["id"] != slot_id:
        errs.append(f"brief id '{obj.get('id')}' != slot id '{slot_id}'")
    if not obj.get("channels"):
        errs.append("missing 'channels'")
    return errs


# --------------------------------------------------------------------------- #
# orchestration: run once, retry once on parse/validation failure, then fail
# --------------------------------------------------------------------------- #
def run_job(prompt: str, voice_text: str, validate, model: str = DEFAULT_MODEL) -> dict:
    attempt_prompt = prompt
    last_err = None
    for attempt in (1, 2):
        stdout = run_claude(attempt_prompt, voice_text, model)
        result_text = extract_result(stdout)
        try:
            obj = parse_model_json(result_text)
            errs = validate(obj)
            if not errs:
                return obj
            last_err = "validation failed: " + "; ".join(errs)
        except json.JSONDecodeError as exc:
            last_err = f"output was not valid JSON ({exc})"
        if attempt == 1:
            print(f"  attempt 1 failed ({last_err}); retrying once...", file=sys.stderr)
            attempt_prompt = (
                prompt
                + f"\n\nYour previous reply could not be used: {last_err}\n"
                + "Return ONLY valid JSON matching the schema. First character must be '{'."
            )
    raise JobError(f"job failed after retry: {last_err}")


# --------------------------------------------------------------------------- #
# voice cascade helpers
# --------------------------------------------------------------------------- #
def find_profile_dir(root: Path, profile_slug: str) -> Path:
    """Locate projects/*/profiles/<profile_slug>/ under root.

    Raises JobError if not found or ambiguous.
    """
    matches = list(root.glob(f"projects/*/profiles/{profile_slug}"))
    matches = [m for m in matches if m.is_dir()]
    if not matches:
        raise JobError(
            f"profile '{profile_slug}' not found under {root}/projects/*/profiles/"
        )
    if len(matches) > 1:
        raise JobError(
            f"profile '{profile_slug}' is ambiguous — found in multiple projects: "
            + ", ".join(str(m) for m in matches)
        )
    return matches[0]


def find_channel_dir(root: Path, channel_slug: str) -> Path:
    """Locate projects/*/profiles/*/channels/<channel_slug>/ under root."""
    matches = list(root.glob(f"projects/*/profiles/*/channels/{channel_slug}"))
    matches = [m for m in matches if m.is_dir()]
    if not matches:
        raise JobError(
            f"channel '{channel_slug}' not found under "
            f"{root}/projects/*/profiles/*/channels/"
        )
    if len(matches) > 1:
        raise JobError(
            f"channel '{channel_slug}' is ambiguous — found in multiple profiles: "
            + ", ".join(str(m) for m in matches)
        )
    return matches[0]


def build_voice_cascade(profile_dir: Path, platforms: list = None) -> str:
    """Compose the VOICE CASCADE: project voice + profile voice + channel guidelines.

    project voice    = projects/<slug>/project.md body
    profile voice    = profiles/<slug>/profile.md body
    channel guidelines = channels/<channel-slug>/guidelines.md
                         (one file per channel whose platform matches `platforms`)

    Returns a single string ready to pipe as stdin to claude.
    """
    parts = []

    # project voice (grandparent of profile_dir)
    project_dir = profile_dir.parent.parent  # profiles/<slug> → project/<slug>
    project_md = project_dir / "project.md"
    if project_md.exists():
        parts.append("--- PROJECT VOICE ---\n" + project_md.read_text(encoding="utf-8").strip())

    # profile voice
    profile_md = profile_dir / "profile.md"
    if profile_md.exists():
        parts.append("--- PROFILE VOICE ---\n" + profile_md.read_text(encoding="utf-8").strip())

    # channel guidelines (for the relevant platforms)
    channels_dir = profile_dir / "channels"
    if channels_dir.is_dir():
        for channel_path in sorted(channels_dir.iterdir()):
            if not channel_path.is_dir():
                continue
            channel_md = channel_path / "channel.md"
            guidelines_md = channel_path / "guidelines.md"
            # determine the platform for this channel
            platform = None
            if channel_md.exists():
                txt = channel_md.read_text(encoding="utf-8")
                m = re.search(r"^platform:\s*(\S+)", txt, re.MULTILINE)
                if m:
                    platform = m.group(1).lower().rstrip("\"'")
            if platforms and platform and platform not in [p.lower() for p in platforms]:
                continue  # skip channels not in the target platform list
            if guidelines_md.exists():
                g = guidelines_md.read_text(encoding="utf-8").strip()
                if g:
                    label = f"--- CHANNEL GUIDELINES ({channel_path.name}) ---"
                    parts.append(label + "\n" + g)

    return "\n\n".join(parts)


def read_channel_guidelines_for_platform(profile_dir: Path, platform: str) -> str:
    """Return guidelines text for a specific platform from the channel dirs."""
    channels_dir = profile_dir / "channels"
    if not channels_dir.is_dir():
        return ""
    for channel_path in sorted(channels_dir.iterdir()):
        if not channel_path.is_dir():
            continue
        channel_md = channel_path / "channel.md"
        guidelines_md = channel_path / "guidelines.md"
        if channel_md.exists():
            txt = channel_md.read_text(encoding="utf-8")
            m = re.search(r"^platform:\s*(\S+)", txt, re.MULTILINE)
            if m and m.group(1).lower().rstrip("\"'") == platform.lower():
                if guidelines_md.exists():
                    return guidelines_md.read_text(encoding="utf-8").strip()
    return ""


def recent_history(content_dir: Path, limit: int = 20) -> str:
    """Titles + pillars of recent planned posts, so the calendar doesn't repeat."""
    items = []
    for plan in content_dir.glob("plan-*.json"):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for p in data.get("posts", []) if isinstance(data, dict) else []:
            items.append((p.get("date") or "", p.get("working_title") or p.get("pillar") or "", p.get("pillar") or ""))
    items.sort(reverse=True)
    lines = [f"- {t} (pillar: {pil})" for _d, t, pil in items[:limit] if t]
    return "\n".join(lines) if lines else "(none yet)"


# --------------------------------------------------------------------------- #
# job builders
# --------------------------------------------------------------------------- #
def channel_slug_map(profile_dir: Path) -> dict:
    """Map platform name -> channel slug for a profile (e.g. 'tiktok' ->
    'movie-and-talk-tiktok'), so a generated plan that names channels by
    platform can be normalized to the real slugs the indexer requires.
    Assumes one channel per platform."""
    out = {}
    channels_dir = profile_dir / "channels"
    if channels_dir.is_dir():
        for channel_path in sorted(channels_dir.iterdir()):
            channel_md = channel_path / "channel.md"
            if channel_path.is_dir() and channel_md.exists():
                m = re.search(r"^platform:\s*(\S+)", channel_md.read_text(encoding="utf-8"), re.MULTILINE)
                if m:
                    out[m.group(1).lower().rstrip("\"'")] = channel_path.name
    return out


def do_plan(root: Path, profile_slug: str, period: str, platforms, cadence, focus):
    profile_dir = find_profile_dir(root, profile_slug)
    profile_md = profile_dir / "profile.md"
    if not profile_md.exists():
        raise JobError(f"profile.md not found: {profile_md}")
    content_dir = profile_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)

    # Build VOICE CASCADE (project + profile + targeted channel guidelines)
    voice_text = build_voice_cascade(profile_dir, platforms)
    if not voice_text.strip():
        raise JobError(f"could not build voice cascade for profile '{profile_slug}'")

    # Per-profile brief spec: the same hard output rules the brief job honors.
    # The planner needs them too — e.g. "one carousel reused as a reel across both
    # platforms" means a slot should target BOTH channels, not split into one post
    # per platform. Without this the calendar drifts from how the posts are produced.
    brief_spec_file = profile_dir / "brief-spec.md"
    brief_spec = brief_spec_file.read_text(encoding="utf-8").strip() if brief_spec_file.exists() else ""

    base = (PROMPTS / "plan.txt").read_text(encoding="utf-8")
    params = (
        "\n\n--- PARAMETERS ---\n"
        f"profile-slug: {profile_slug}\n"
        f"period: {period}\n"
        f"platforms: {', '.join(platforms)}\n"
        f"cadence (posts per platform per week): {cadence}\n"
        f"focus: {focus or '(none)'}\n"
        "\n--- RECENT HISTORY (do not repeat) ---\n"
        f"{recent_history(content_dir)}\n"
    )
    if brief_spec:
        params += (
            "\n--- PROFILE BRIEF SPEC (how posts are produced — plan accordingly) ---\n"
            f"{brief_spec}\n"
        )
    obj = run_job(base + params, voice_text, validate_plan)

    # Normalize channel refs: the model often emits platform names ('tiktok')
    # instead of real channel slugs ('movie-and-talk-tiktok'). Remap so the
    # strict indexer accepts the plan and the server can start.
    cmap = channel_slug_map(profile_dir)
    valid = set(cmap.values())
    for post in obj.get("posts", []):
        post["channels"] = [
            ch if ch in valid else cmap.get(str(ch).lower(), ch)
            for ch in post.get("channels", [])
        ]
        # A fresh plan is a batch of ideas — nothing has been written or reviewed
        # yet. The model sometimes emits an advanced status ('approved',
        # 'published'); force every new slot back to 'planned' so the pipeline
        # state machine starts from the front.
        post["status"] = "planned"

    fname = "plan-" + re.sub(r"[^0-9a-zA-Z]+", "-", period).strip("-") + ".json"
    out = content_dir / fname
    out.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}  ({len(obj.get('posts', []))} slots)")
    print("Next: review slots, then `generate.py brief <profile-slug> <id>` for approved ones.")


def find_slot(content_dir: Path, post_id: str):
    for plan in sorted(content_dir.glob("plan-*.json")):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for p in data.get("posts", []) if isinstance(data, dict) else []:
            if p.get("id") == post_id:
                return p
    return None


def do_brief(root: Path, profile_slug: str, post_id: str):
    profile_dir = find_profile_dir(root, profile_slug)
    profile_md = profile_dir / "profile.md"
    if not profile_md.exists():
        raise JobError(f"profile.md not found: {profile_md}")
    content_dir = profile_dir / "content"
    slot = find_slot(content_dir, post_id)
    if slot is None:
        raise JobError(f"slot '{post_id}' not found in any plan-*.json under {content_dir}")

    constraints = json.loads((PROMPTS / "platform-constraints.json").read_text(encoding="utf-8"))
    # slots may target multiple channels; use first channel's platform for constraints
    slot_channels = slot.get("channels") or []
    plat = slot.get("platform") or (slot_channels[0] if slot_channels else None)
    plat_cfg = constraints.get(plat, {}) if plat else {}

    # VOICE CASCADE: project + profile + channel guidelines for the relevant platform
    voice_text = build_voice_cascade(profile_dir, [plat] if plat else None)

    # Per-profile brief spec: free-text requirements (caption length, hashtag
    # count, format leanings) that every post for this profile must honor.
    brief_spec_file = profile_dir / "brief-spec.md"
    brief_spec = brief_spec_file.read_text(encoding="utf-8").strip() if brief_spec_file.exists() else ""

    brief_spec_block = (
        "--- PROFILE BRIEF SPEC (per-field rules — override defaults below) ---\n"
        f"{brief_spec}\n"
        "--- END PROFILE BRIEF SPEC ---"
        if brief_spec else
        "(no per-field overrides — use your best judgment for the content type and platform)"
    )
    base = (PROMPTS / "brief.txt").read_text(encoding="utf-8").replace(
        "{{PROFILE_BRIEF_SPEC}}", brief_spec_block
    )
    params = (
        "\n\n--- APPROVED SLOT ---\n"
        f"{json.dumps(slot, indent=2, ensure_ascii=False)}\n"
        f"\n--- PLATFORM CONSTRAINTS ({plat}) ---\n"
        f"{json.dumps(plat_cfg, indent=2, ensure_ascii=False)}\n"
    )
    obj = run_job(base + params, voice_text,
                  lambda o: validate_brief(o, post_id))

    briefs = content_dir / "briefs"
    briefs.mkdir(parents=True, exist_ok=True)
    out = briefs / f"{post_id}.json"
    out.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    print("Next: re-index so posts.status picks up the new brief.")


def do_revise(root: Path, profile_slug: str, post_id: str, instruction: str):
    """Revise an existing slot (idea) or brief (draft) using a user instruction.

    - Ideas (no brief file): updates slot fields in the plan-*.json in place.
    - Drafts (brief file exists): overwrites the brief JSON and bumps nothing
      (fileops handles the version bump after calling this).
    """
    profile_dir = find_profile_dir(root, profile_slug)
    content_dir = profile_dir / "content"
    slot = find_slot(content_dir, post_id)
    if slot is None:
        raise JobError(f"slot '{post_id}' not found in any plan-*.json under {content_dir}")

    brief_file = content_dir / "briefs" / f"{post_id}.json"
    is_draft = brief_file.exists()

    constraints = json.loads((PROMPTS / "platform-constraints.json").read_text(encoding="utf-8"))

    if is_draft:
        current = json.loads(brief_file.read_text(encoding="utf-8"))
        plat = current.get("platform") or (slot.get("channels") or [""])[0]
    else:
        current = slot
        plat = slot.get("platform") or (slot.get("channels") or [""])[0]

    plat_cfg = constraints.get(plat, {}) if plat else {}
    voice_text = build_voice_cascade(profile_dir, [plat] if plat else None)

    brief_spec_file = profile_dir / "brief-spec.md"
    brief_spec = brief_spec_file.read_text(encoding="utf-8").strip() if brief_spec_file.exists() else ""

    kind = "BRIEF" if is_draft else "SLOT"
    base = (PROMPTS / "revise.txt").read_text(encoding="utf-8")
    params = (
        f"\n\n--- CURRENT {kind} ---\n"
        f"{json.dumps(current, indent=2, ensure_ascii=False)}\n"
        f"\n--- REVISION INSTRUCTION ---\n{instruction}\n"
        f"\n--- PLATFORM CONSTRAINTS ({plat}) ---\n"
        f"{json.dumps(plat_cfg, indent=2, ensure_ascii=False)}\n"
    )
    if brief_spec:
        params += f"\n--- PROFILE BRIEF SPEC ---\n{brief_spec}\n"

    validate = (lambda o: validate_brief(o, post_id)) if is_draft else validate_revise_idea
    obj = run_job(base + params, voice_text, validate)

    if is_draft:
        brief_file.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"revised brief for {post_id}")
    else:
        # Merge revised fields back into the plan file slot in place.
        for plan in sorted(content_dir.glob("plan-*.json")):
            try:
                data = json.loads(plan.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for p in data.get("posts", []) if isinstance(data, dict) else []:
                if p.get("id") == post_id:
                    for k, v in obj.items():
                        if k != "id":
                            p[k] = v
                    plan.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"revised slot for {post_id}")
                    return
        raise JobError(f"could not write back slot '{post_id}' to any plan file")


def do_refine_guidelines(root: Path, channel_slug: str, raw_text: str) -> str:
    """AI-polish rough guideline notes into clean, structured context markdown.

    Resolves projects/*/profiles/*/channels/<channel_slug>/; uses the parent
    profile.md (and project.md) as voice context. Prints to stdout — does NOT
    save (fileops saves after user review).
    """
    channel_dir = find_channel_dir(root, channel_slug)
    profile_dir = channel_dir.parent.parent  # channels/<slug> → profile/<slug>

    # build voice context (project + profile only, no channel guidelines — that's what we're writing)
    profile_md = profile_dir / "profile.md"
    project_md = profile_dir.parent.parent / "project.md"
    context_parts = []
    if project_md.exists():
        context_parts.append("--- PROJECT VOICE ---\n" + project_md.read_text(encoding="utf-8").strip())
    if profile_md.exists():
        context_parts.append("--- PROFILE VOICE ---\n" + profile_md.read_text(encoding="utf-8").strip())
    context = "\n\n".join(context_parts)

    prompt = (PROMPTS / "refine-guidelines.txt").read_text(encoding="utf-8")
    if context:
        prompt += "\n\n--- VOICE CONTEXT (context only) ---\n" + context
    out = extract_result(run_claude(prompt, raw_text)).strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\n", "", out)
        out = re.sub(r"\n```\s*$", "", out)
    return out.strip()


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Synchronous claude -p content pipeline")
    ap.add_argument("--workspace", default=".", help="workspace root (default: cwd)")
    sub = ap.add_subparsers(dest="job", required=True)

    pp = sub.add_parser("plan", help="generate a content calendar skeleton")
    pp.add_argument("profile", help="profile slug (resolves under projects/*/profiles/<slug>/)")
    pp.add_argument("--period", required=True, help='e.g. "2026-06-15 to 2026-06-28"')
    pp.add_argument("--platforms", default="instagram", help="comma-separated platform names")
    pp.add_argument("--cadence", default=3, type=int, help="posts per platform per week")
    pp.add_argument("--focus", default=None, help="optional creative steer for this period")

    pb = sub.add_parser("brief", help="expand one approved slot into full content")
    pb.add_argument("profile", help="profile slug")
    pb.add_argument("post_id", help="slot id from plan-*.json")

    pv = sub.add_parser("revise", help="revise an existing slot or brief with an instruction")
    pv.add_argument("profile", help="profile slug")
    pv.add_argument("post_id", help="slot id")
    pv.add_argument("--instruction", required=True, help='e.g. "punchier hook, caption under 200 chars"')

    pr = sub.add_parser("refine-guidelines",
                        help="read rough guideline notes from stdin, print refined markdown")
    pr.add_argument("channel", help="channel slug (resolves under projects/*/profiles/*/channels/<slug>/)")

    args = ap.parse_args()
    root = Path(args.workspace).resolve()
    try:
        if args.job == "plan":
            platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
            do_plan(root, args.profile, args.period, platforms, args.cadence, args.focus)
        elif args.job == "brief":
            do_brief(root, args.profile, args.post_id)
        elif args.job == "revise":
            do_revise(root, args.profile, args.post_id, args.instruction)
        else:  # refine-guidelines
            sys.stdout.write(do_refine_guidelines(root, args.channel, sys.stdin.read()))
    except JobError as exc:
        print(f"\nJOB FAILED: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
