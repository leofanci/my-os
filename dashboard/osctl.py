"""osctl.py — the single mutation entry point for the GTM OS AI agent.

Wraps dashboard/fileops.py mutations as a stdlib argparse CLI. Each subcommand
validates input, calls fileops (which writes authored files and reindexes), and
prints exactly one JSON line. The chat agent is allowed to mutate state ONLY
through this CLI, so the authored-files-are-truth invariant cannot be bypassed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root
from dashboard import db, fileops  # noqa: E402
from core.ids import (  # noqa: E402
    bare_slug,
    build_catalog,
    build_id_registry,
    build_project_sections,
    catalog_as_text,
    describe_id,
    parse_id,
    resolve_section,
)


def _emit(obj, ok=True):
    print(json.dumps({"ok": ok, **obj}, ensure_ascii=False))
    return 0 if ok else 1


def _fields(args, keys):
    """Collect provided (non-None) attrs into a fileops fields dict."""
    return {k: getattr(args, k) for k in keys if getattr(args, k) is not None}


def _build_parser():
    parser = argparse.ArgumentParser(prog="osctl", description="GTM OS mutation CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("tree", help="Print current project/profile/channel structure")
    def _tree(a):
        lines = []
        for proj in db.tree():
            lines.append(f"{proj['slug']} ({proj.get('kind') or proj.get('type')})")
            for prof in proj.get("profiles", []):
                lines.append(f"  profile {prof['slug']} \"{prof['name']}\"")
                for ch in prof.get("channels", []):
                    lines.append(f"    channel {ch['slug']} ({ch.get('platform')})")
        return {"tree": "\n".join(lines) if lines else "(no projects yet)"}
    p.set_defaults(_run=_tree)

    p = sub.add_parser("create-project")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--kind")
    p.add_argument("--priority")
    p.add_argument("--status")
    p.add_argument("--hours-per-week", dest="hours_per_week")
    p.add_argument("--voice")
    p.set_defaults(_run=lambda a: fileops.create_project(
        a.slug, _fields(a, ["name", "kind", "priority", "status", "hours_per_week", "voice"])))

    p = sub.add_parser("create-profile")
    p.add_argument("--project", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--topic")
    p.set_defaults(_run=lambda a: fileops.create_profile(
        a.project, a.slug, _fields(a, ["name", "topic"])))

    p = sub.add_parser("create-channel")
    p.add_argument("--profile", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--handle", default="")
    p.set_defaults(_run=lambda a: fileops.create_channel(
        a.profile, a.slug, a.platform, a.handle))

    p = sub.add_parser("create-intake", help="Scaffold strategy/intake.md for a project")
    p.add_argument("--project", required=True)
    p.set_defaults(_run=lambda a: fileops.create_intake(a.project))

    p = sub.add_parser("update-intake", help="Replace strategy/intake.md (--text or stdin)")
    p.add_argument("--project", required=True)
    p.add_argument("--text", default="")
    def _update_intake(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        return fileops.write_intake(a.project, text)
    p.set_defaults(_run=_update_intake)

    p = sub.add_parser("create-technical", help="Scaffold technical.md for a project")
    p.add_argument("--project", required=True)
    p.set_defaults(_run=lambda a: fileops.create_technical(a.project))

    p = sub.add_parser("update-technical", help="Replace technical.md (--text or stdin)")
    p.add_argument("--project", required=True)
    p.add_argument("--text", default="")
    def _update_technical(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        return fileops.write_technical(a.project, text)
    p.set_defaults(_run=_update_technical)

    p = sub.add_parser("get-subsections", help="Per-project tab subsection config")
    p.add_argument("--project", required=True)
    def _get_subsections(a):
        return {"project": a.project, "subsections": fileops.read_subsections(a.project)}
    p.set_defaults(_run=_get_subsections)

    p = sub.add_parser("update-subsections",
                       help="Replace subsection list for intake, technical, or roadmap doc")
    p.add_argument("--project", required=True)
    p.add_argument("--doc", required=True, choices=["intake", "technical", "roadmap"])
    p.add_argument("--subsections", required=True,
                   help="Comma- or newline-separated subsection titles")
    def _update_subsections(a):
        titles = fileops.parse_subsections_arg(a.subsections)
        if not titles:
            raise fileops.ActionError("at least one subsection title required")
        return fileops.update_subsections(a.project, a.doc, titles)
    p.set_defaults(_run=_update_subsections)

    p = sub.add_parser("add-subsection", help="Append one subsection to a project doc config")
    p.add_argument("--project", required=True)
    p.add_argument("--doc", required=True, choices=["intake", "technical", "roadmap"])
    p.add_argument("--title", required=True)
    p.set_defaults(_run=lambda a: fileops.add_subsection(a.project, a.doc, a.title))

    p = sub.add_parser("update-validation-tab",
                       help="Set which intake subsections show on Problem & validation tab")
    p.add_argument("--project", required=True)
    p.add_argument("--subsections", required=True,
                   help="Comma- or newline-separated titles (must exist in intake list)")
    def _update_validation_tab(a):
        titles = fileops.parse_subsections_arg(a.subsections)
        if not titles:
            raise fileops.ActionError("at least one subsection title required")
        return fileops.update_validation_tab(a.project, titles)
    p.set_defaults(_run=_update_validation_tab)

    p = sub.add_parser("create-memo", help="Create next versioned strategy memo JSON")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, dest="memo_type")
    p.add_argument("--summary")
    p.add_argument("--recommendation")
    p.add_argument("--problem-statement", dest="problem_statement")
    p.add_argument("--body-json", dest="body_json", default="",
                   help="Extra memo fields as JSON (--body-json or stdin when --text empty)")
    def _create_memo(a):
        fields = _fields(a, ["summary", "recommendation", "problem_statement"])
        body_extra = None
        raw = (a.body_json or "").strip()
        if raw:
            body_extra = json.loads(raw)
        return fileops.create_memo(a.project, a.memo_type, fields, body_extra=body_extra)
    p.set_defaults(_run=_create_memo)

    p = sub.add_parser("create-experiment", help="Create strategy/experiments/<stem>.json")
    p.add_argument("--project", required=True)
    p.add_argument("--assumption", required=True)
    p.add_argument("--stem")
    p.add_argument("--success-criteria", dest="success_criteria")
    p.add_argument("--kill-criteria", dest="kill_criteria")
    p.set_defaults(_run=lambda a: fileops.create_experiment(
        a.project, _fields(a, ["assumption", "stem", "success_criteria", "kill_criteria"])))

    p = sub.add_parser("update-experiment", help="Patch an existing experiment JSON")
    p.add_argument("--project", required=True)
    p.add_argument("--stem", required=True)
    p.add_argument("--assumption")
    p.add_argument("--success-criteria", dest="success_criteria")
    p.add_argument("--kill-criteria", dest="kill_criteria")
    p.set_defaults(_run=lambda a: fileops.update_experiment(
        a.project, a.stem, _fields(a, ["assumption", "success_criteria", "kill_criteria"])))

    p = sub.add_parser("update-memo", help="Patch an existing memo JSON (same version, in place)")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, dest="memo_type")
    p.add_argument("--version", required=True, type=int)
    p.add_argument("--summary")
    p.add_argument("--recommendation")
    p.add_argument("--problem-statement", dest="problem_statement")
    p.add_argument("--body-json", dest="body_json", default="",
                   help="Extra memo fields as JSON (--body-json or stdin when --text empty)")
    def _update_memo(a):
        fields = _fields(a, ["summary", "recommendation", "problem_statement"])
        raw = (a.body_json or "").strip()
        if raw:
            fields.update(json.loads(raw))
        return fileops.update_memo(a.project, a.memo_type, a.version, fields)
    p.set_defaults(_run=_update_memo)

    p = sub.add_parser("delete-memo", help="Delete one memo version JSON")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, dest="memo_type")
    p.add_argument("--version", required=True, type=int)
    p.set_defaults(_run=lambda a: fileops.delete_memo(a.project, a.memo_type, a.version))

    p = sub.add_parser("delete-experiment", help="Delete strategy/experiments/<stem>.json")
    p.add_argument("--project", required=True)
    p.add_argument("--stem", required=True)
    p.set_defaults(_run=lambda a: fileops.delete_experiment(a.project, a.stem))

    p = sub.add_parser("create-product", help="Scaffold products/<slug>/ under a project")
    p.add_argument("--project", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--type")
    p.add_argument("--status")
    p.set_defaults(_run=lambda a: fileops.create_product(
        a.project, a.slug, _fields(a, ["name", "type", "status"])))

    p = sub.add_parser("add-feature", help="Append a roadmap checklist item")
    p.add_argument("--product", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--section", default="Next")
    p.add_argument("--why", default=None, help="One-line description after title")
    p.add_argument("--priority", default=None, choices=["critical", "high", "normal", "low"])
    p.set_defaults(_run=lambda a: fileops.add_feature(
        a.product, _fields(a, ["title", "section", "why", "priority"])))

    p = sub.add_parser("update-feature", help="Patch one roadmap checklist line")
    p.add_argument("--product", required=True)
    p.add_argument("--id", required=True, dest="feature_id")
    p.add_argument("--title")
    p.add_argument("--why")
    p.add_argument("--section")
    p.add_argument("--priority")
    p.set_defaults(_run=lambda a: fileops.update_feature(
        a.product, a.feature_id, _fields(a, ["title", "why", "section", "priority"])))

    p = sub.add_parser("delete-feature", help="Remove one roadmap checklist line")
    p.add_argument("--product", required=True)
    p.add_argument("--id", required=True, dest="feature_id")
    p.set_defaults(_run=lambda a: fileops.delete_feature(a.product, a.feature_id))

    p = sub.add_parser("update-roadmap", help="Replace products/<slug>/roadmap.md (--text or stdin)")
    p.add_argument("--product", required=True)
    p.add_argument("--text", default="")
    def _update_roadmap(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        return fileops.write_roadmap(a.product, text)
    p.set_defaults(_run=_update_roadmap)

    # add-post fields map to fileops._POST_FIELDS (date, pillar, working_title)
    # + channels; hook/angle are not real post fields, so they are not exposed.
    p = sub.add_parser("add-post")
    p.add_argument("--profile", required=True)
    p.add_argument("--working-title", dest="working_title")
    p.add_argument("--pillar")
    p.add_argument("--date")
    p.add_argument("--channels")
    p.add_argument("--status", choices=["planned", "published"],
                   help="published logs an already-posted item (requires --date)")
    p.set_defaults(_run=lambda a: fileops.add_post(
        a.profile, _fields(a, ["working_title", "pillar", "date", "channels", "status"])))

    # --title is intentionally NOT argparse-required: fileops.create_activity
    # validates it and returns a JSON error, keeping validation in one place.
    p = sub.add_parser("create-activity")
    p.add_argument("--entity", required=True)
    p.add_argument("--title")
    p.add_argument("--date")
    p.add_argument("--date-end", dest="date_end")
    p.add_argument("--type")
    p.add_argument("--priority")
    p.set_defaults(_run=lambda a: fileops.create_activity(
        _fields(a, ["entity", "title", "date", "date_end", "type", "priority"])))

    p = sub.add_parser("create-milestone")
    p.add_argument("--title", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--entity")
    p.add_argument("--type")
    p.add_argument("--entity-type", dest="entity_type")
    p.add_argument("--date-end", dest="date_end")
    p.add_argument("--notes")
    p.add_argument("--priority")
    p.set_defaults(_run=lambda a: fileops.create_milestone(
        _fields(a, ["title", "date", "entity", "type", "entity_type",
                    "date_end", "notes", "priority"])))

    p = sub.add_parser("mark-done")
    p.add_argument("--title", required=True)
    p.add_argument("--entity", required=True)
    p.set_defaults(_run=lambda a: fileops.mark_activity_done(a.title, a.entity))

    p = sub.add_parser("update-post")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--working-title", dest="working_title")
    p.add_argument("--pillar")
    p.add_argument("--date")
    p.add_argument("--channels")
    p.add_argument("--format")
    p.add_argument("--objective")
    p.add_argument("--platform")
    p.set_defaults(_run=lambda a: fileops.update_post(
        a.id, _fields(a, ["working_title", "pillar", "date", "channels", "format", "objective", "platform"])))

    p = sub.add_parser("set-status")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--status", required=True)
    p.set_defaults(_run=lambda a: fileops.set_status(a.id, a.status))

    # edit (rename) commands — the slug stays fixed; metadata/name are editable.

    p = sub.add_parser("update-profile")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--topic")
    p.set_defaults(_run=lambda a: fileops.update_profile(
        a.slug, _fields(a, ["name", "topic"])))

    p = sub.add_parser("get-brief-spec",
                       help="Read one profile brief-spec (default br1), or list all with --list")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="br1", dest="brief_id")
    p.add_argument("--list", action="store_true")
    p.set_defaults(_run=lambda a: (
        {"profile": a.profile, "specs": fileops.list_brief_specs(a.profile)}
        if a.list else fileops.get_brief_spec(a.profile, a.brief_id)
    ))

    p = sub.add_parser("update-brief-spec",
                       help="Replace one profile brief-spec (default br1)")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="br1", dest="brief_id")
    p.add_argument("--platforms")
    p.add_argument("--text", default="")
    def _update_brief_spec(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("brief spec text required (--text or stdin)")
        return fileops.write_brief_spec(a.profile, text, a.brief_id, a.platforms)
    p.set_defaults(_run=_update_brief_spec)

    p = sub.add_parser("create-brief-spec",
                       help="Add a new brief-spec to a profile (mints the next br id)")
    p.add_argument("--profile", required=True)
    p.add_argument("--platforms", default="all")
    p.add_argument("--text", default="")
    def _create_brief_spec(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("brief spec text required (--text or stdin)")
        return fileops.create_brief_spec(a.profile, text, a.platforms)
    p.set_defaults(_run=_create_brief_spec)

    p = sub.add_parser("delete-brief-spec", help="Delete a profile brief-spec by id")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", required=True, dest="brief_id")
    p.set_defaults(_run=lambda a: fileops.delete_brief_spec(a.profile, a.brief_id))

    p = sub.add_parser("get-voice",
                       help="Read one profile voice (default vc1), or list all with --list")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="vc1", dest="voice_id")
    p.add_argument("--list", action="store_true")
    p.set_defaults(_run=lambda a: (
        {"profile": a.profile, "voices": fileops.list_voices(a.profile)}
        if a.list else fileops.get_voice(a.profile, a.voice_id)
    ))

    p = sub.add_parser("update-voice", help="Replace one profile voice (default vc1)")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", default="vc1", dest="voice_id")
    p.add_argument("--platforms")
    p.add_argument("--text", default="")
    def _update_voice(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("voice text required (--text or stdin)")
        return fileops.update_voice(a.profile, text, a.voice_id, a.platforms)
    p.set_defaults(_run=_update_voice)

    p = sub.add_parser("create-voice", help="Add a new voice to a profile (mints the next vc id)")
    p.add_argument("--profile", required=True)
    p.add_argument("--platforms", default="all")
    p.add_argument("--text", default="")
    def _create_voice(a):
        text = a.text
        if not text.strip():
            text = sys.stdin.read()
        if not text.strip():
            raise fileops.ActionError("voice text required (--text or stdin)")
        return fileops.create_voice(a.profile, text, a.platforms)
    p.set_defaults(_run=_create_voice)

    p = sub.add_parser("delete-voice", help="Delete a profile voice by id")
    p.add_argument("--profile", required=True)
    p.add_argument("--id", required=True, dest="voice_id")
    p.set_defaults(_run=lambda a: fileops.delete_voice(a.profile, a.voice_id))

    p = sub.add_parser("update-project")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--kind")
    p.add_argument("--priority")
    p.add_argument("--status")
    p.add_argument("--hours-per-week", dest="hours_per_week")
    p.set_defaults(_run=lambda a: fileops.update_project(
        a.slug, _fields(a, ["name", "kind", "priority", "status", "hours_per_week"])))

    p = sub.add_parser("update-channel")
    p.add_argument("--slug", required=True)
    p.add_argument("--platform")
    p.add_argument("--handle")
    p.add_argument("--name")
    p.add_argument("--bio")
    p.set_defaults(_run=lambda a: fileops.update_channel(
        a.slug, _fields(a, ["platform", "handle", "name", "bio"])))

    p = sub.add_parser("update-milestone")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--title")
    p.add_argument("--date")
    p.add_argument("--date-end", dest="date_end")
    p.add_argument("--type")
    p.add_argument("--entity")
    p.add_argument("--entity-type", dest="entity_type")
    p.add_argument("--notes")
    p.add_argument("--priority")
    p.set_defaults(_run=lambda a: fileops.update_milestone(a.id, _fields(
        a, ["title", "date", "date_end", "type", "entity", "entity_type", "notes", "priority"])))

    # Content generation — same generate.py jobs the dashboard buttons run.
    p = sub.add_parser("generate-brief",
                       help="Run the brief job for a planned/approved slot (same as Write button)")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--instruction", default="")
    p.add_argument("--spec", dest="brief_id", default=None,
                   help="brief-spec id to use, e.g. br2 (default: post's stored id, else br1)")
    p.add_argument("--voice", dest="voice_id", default=None,
                   help="voice id to use, e.g. vc2 (default: post's stored id, else vc1)")
    p.set_defaults(_run=lambda a: fileops.generate_brief(
        a.id, a.instruction or None, brief_id=a.brief_id, voice_id=a.voice_id))

    p = sub.add_parser("update-brief",
                       help="Create or change a brief from natural language (primary chat path)")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--instruction", default="")
    p.add_argument("--spec", dest="brief_id", default=None,
                   help="brief-spec id to use, e.g. br2 (default: post's stored id, else br1)")
    p.add_argument("--voice", dest="voice_id", default=None,
                   help="voice id to use, e.g. vc2 (default: post's stored id, else vc1)")
    p.set_defaults(_run=lambda a: fileops.update_brief(
        a.id, a.instruction or None, brief_id=a.brief_id, voice_id=a.voice_id))

    p = sub.add_parser("generate-plan",
                       help="Run the plan job for a profile (same as Generate ideas button)")
    p.add_argument("--profile", required=True)
    p.add_argument("--period", required=True)
    p.add_argument("--platforms", default="")
    p.add_argument("--cadence", default="")
    p.add_argument("--focus", default="")
    p.add_argument("--brief-counts", default="", dest="brief_counts",
                   help='e.g. "br1:5,br2:2" — only meaningful when the profile has >1 brief-spec')
    p.add_argument("--voice-counts", default="", dest="voice_counts",
                   help='e.g. "vc1:5,vc2:2" — only meaningful when the profile has >1 voice')
    p.add_argument("--dates", action="store_true",
                   help="assign a date to each post (default: leave unscheduled)")
    def _generate_plan(a):
        params = {"period": a.period}
        if a.platforms:
            params["platforms"] = a.platforms
        if a.cadence not in (None, ""):
            params["cadence"] = a.cadence
        if a.focus:
            params["focus"] = a.focus
        if a.brief_counts:
            params["brief_counts"] = a.brief_counts
        if a.voice_counts:
            params["voice_counts"] = a.voice_counts
        if a.dates:
            params["dates"] = True
        return fileops.run_plan(a.profile, params)
    p.set_defaults(_run=_generate_plan)

    p = sub.add_parser("add-slide", help="Append one slide_overlays row to a post brief")
    p.add_argument("--id", required=True, dest="post_id")
    p.add_argument("--overlay", required=True)
    p.set_defaults(_run=lambda a: fileops.add_slide_overlay(a.post_id, a.overlay))

    p = sub.add_parser("revise-post",
                       help="Revise a slot or draft via generate.py (same as Revise button)")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--instruction", required=True)
    p.add_argument("--spec", dest="brief_id", default=None,
                   help="brief-spec id to use, e.g. br2 (default: post's stored id, else br1)")
    p.add_argument("--voice", dest="voice_id", default=None,
                   help="voice id to use, e.g. vc2 (default: post's stored id, else vc1)")
    p.set_defaults(_run=lambda a: fileops.revise_post(
        a.id, a.instruction, brief_id=a.brief_id, voice_id=a.voice_id))

    # --- read commands (no mutations) ---

    p = sub.add_parser("research-signal",
                       help="Real online-discourse signal for a topic via last30days "
                            "(zero-config sources, no API keys required)")
    p.add_argument("--query", required=True)
    p.add_argument("--max-clusters", type=int, default=5, dest="max_clusters")
    p.set_defaults(_run=lambda a: fileops.research_signal(a.query, max_clusters=a.max_clusters))

    p = sub.add_parser("get-posts", help="List posts, optionally filtered by profile")
    p.add_argument("--profile", default=None)
    def _get_posts(a):
        rows = db.profile_posts(a.profile) if a.profile else db.posts()
        return {"posts": rows}
    p.set_defaults(_run=_get_posts)

    p = sub.add_parser("get-project", help="Full project data: activities, memos, experiments, features")
    p.add_argument("--slug", required=True)
    def _get_project(a):
        data = db.project(a.slug)
        if data is None:
            raise fileops.ActionError(f"project '{a.slug}' not found")
        reg = build_id_registry(
            db.tree(), db.posts(), root=fileops.ROOT, features=data["features"])
        data["memos"] = fileops.enrich_project_memos(data["memos"], a.slug, reg)
        data["experiments"] = fileops.enrich_project_experiments(data["experiments"], a.slug, reg)
        data["features"] = fileops.enrich_project_features(data["features"], reg)
        data["sections"] = build_project_sections(a.slug, fileops.ROOT, data, registry=reg)
        from core.project_schemas import feature_form_fields

        data["subsections"] = fileops.read_subsections(a.slug)
        from core.ids import subsection_id_map
        data["subsection_ids"] = subsection_id_map(reg, a.slug)
        data["feature"] = feature_form_fields(data["subsections"]["docs"]["roadmap"])
        return {"project": data}
    p.set_defaults(_run=_get_project)

    p = sub.add_parser("read-file", help="Read any authored file by repo-relative path")
    p.add_argument("--path", required=True)
    def _read_file(a):
        repo_root = fileops.ROOT
        target = (repo_root / a.path).resolve()
        if not str(target).startswith(str(repo_root.resolve())):
            raise fileops.ActionError("path outside repo")
        if not target.exists():
            raise fileops.ActionError(f"file not found: {a.path}")
        return {"path": a.path, "content": target.read_text(encoding="utf-8")}
    p.set_defaults(_run=_read_file)

    p = sub.add_parser("get-id-catalog", help="List all canonical IDs (UI skeleton + live entities)")
    p.add_argument("--text", action="store_true", help="Human-readable summary instead of JSON entries")
    def _id_catalog(a):
        entries = build_catalog(db.tree(), root=fileops.ROOT, posts=db.posts())
        if a.text:
            return {"catalog": catalog_as_text(entries), "count": len(entries)}
        return {"entries": entries, "count": len(entries)}
    p.set_defaults(_run=_id_catalog)

    p = sub.add_parser("resolve-id", help="Describe a canonical ID")
    p.add_argument("--id", required=True, dest="id")
    def _resolve_id(a):
        reg = build_id_registry(db.tree(), db.posts(), root=fileops.ROOT)
        parsed = parse_id(a.id)
        if not parsed:
            raise fileops.ActionError(f"not a canonical id: {a.id}")
        ent = reg.resolve(a.id)
        out = {
            "id": a.id,
            "describe": describe_id(a.id, reg),
            "bare": bare_slug(a.id, reg),
            "parsed": parsed,
        }
        if ent:
            out["entry"] = ent
            ref = ent.get("ref") or {}
            if ent.get("kind") == "tab" and ref.get("project") and ref.get("section"):
                pdata = db.project(ref["project"])
                sec = resolve_section(
                    ref["project"], ref["section"], fileops.ROOT,
                    project_data=pdata, registry=reg,
                )
                if sec is not None:
                    out["section"] = sec
            if ent.get("kind") == "slot_field" and ref.get("post") and ref.get("field"):
                post_id, field = ref["post"], ref["field"]
                try:
                    detail = fileops.read_detail(post_id)
                    slot = detail.get("slot") or {}
                    out["field"] = {
                        "post": post_id,
                        "field": field,
                        "scope": "slot",
                        "value": slot.get(field) if field != "channels" else slot.get("channels"),
                    }
                except fileops.ActionError:
                    pass
            elif ent.get("kind") in ("field", "brief_field") and ref.get("post") and ref.get("field"):
                post_id, field = ref["post"], ref["field"]
                try:
                    detail = fileops.read_detail(post_id)
                    brief = detail.get("brief") or {}
                    path = None
                    if detail.get("profile_slug"):
                        prof_dir = fileops._profile_dir(detail["profile_slug"])
                        bf = prof_dir / "content" / "briefs" / f"{post_id}.json"
                        if bf.exists():
                            path = str(bf.relative_to(fileops.ROOT))
                    out["field"] = {
                        "post": post_id,
                        "field": field,
                        "scope": "brief",
                        "path": path,
                        "value": _brief_field_value(brief, field),
                    }
                except fileops.ActionError:
                    pass
            elif ent.get("kind") == "brief" and ref.get("post"):
                post_id = ref["post"]
                try:
                    detail = fileops.read_detail(post_id)
                    out["brief"] = {"post": post_id, "fields": list((detail.get("brief") or {}).keys())}
                except fileops.ActionError:
                    pass
        return out
    p.set_defaults(_run=_resolve_id)

    return parser


def _brief_field_value(brief: dict, field: str):
    if not brief or field.startswith("_"):
        return None
    if field.startswith("slide-"):
        try:
            n = int(field.split("-", 1)[1])
        except (IndexError, ValueError):
            return None
        for item in brief.get("slide_overlays") or []:
            if isinstance(item, dict) and int(item.get("slide") or 0) == n:
                return item.get("overlay")
        return None
    if field.startswith("gen-prompt-"):
        try:
            n = int(field.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None
        prompts = brief.get("gen_prompts") or []
        return prompts[n - 1] if 0 < n <= len(prompts) else None
    return brief.get(field)


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = args._run(args)
    except fileops.ActionError as exc:
        return _emit({"error": str(exc)}, ok=False)
    except Exception as exc:  # noqa: BLE001
        return _emit({"error": repr(exc)}, ok=False)
    return _emit(result)


if __name__ == "__main__":
    raise SystemExit(main())
