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
    p.add_argument("--voice")
    p.set_defaults(_run=lambda a: fileops.create_profile(
        a.project, a.slug, _fields(a, ["name", "topic", "voice"])))

    p = sub.add_parser("create-channel")
    p.add_argument("--profile", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--handle", default="")
    p.set_defaults(_run=lambda a: fileops.create_channel(
        a.profile, a.slug, a.platform, a.handle))

    # add-post fields map to fileops._POST_FIELDS (date, pillar, working_title)
    # + channels; hook/angle are not real post fields, so they are not exposed.
    p = sub.add_parser("add-post")
    p.add_argument("--profile", required=True)
    p.add_argument("--working-title", dest="working_title")
    p.add_argument("--pillar")
    p.add_argument("--date")
    p.add_argument("--channels")
    p.set_defaults(_run=lambda a: fileops.add_post(
        a.profile, _fields(a, ["working_title", "pillar", "date", "channels"])))

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
    p.set_defaults(_run=lambda a: fileops.update_post(
        a.id, _fields(a, ["working_title", "pillar", "date", "channels"])))

    p = sub.add_parser("set-status")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--status", required=True)
    p.set_defaults(_run=lambda a: fileops.set_status(a.id, a.status))

    # edit (rename) commands — the slug stays fixed; metadata/name are editable.

    p = sub.add_parser("update-profile")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--topic")
    p.add_argument("--voice")
    p.add_argument("--brief-spec")
    p.set_defaults(_run=lambda a: fileops.update_profile(
        a.slug, _fields(a, ["name", "topic", "voice", "brief_spec"])))

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

    p = sub.add_parser('patch-brief')
    p.add_argument('--id', required=True, dest='id')
    p.add_argument('--caption')
    p.add_argument('--hook')
    p.add_argument('--catchy-title', dest='catchy_title')
    p.add_argument('--cover-overlay', dest='cover_overlay')
    p.set_defaults(_run=lambda a: fileops.patch_brief(
        a.id, _fields(a, ['caption', 'hook', 'catchy_title', 'cover_overlay'])))

    # --- read commands (no mutations) ---

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
        return {"project": data}
    p.set_defaults(_run=_get_project)

    p = sub.add_parser("read-file", help="Read any authored file by repo-relative path")
    p.add_argument("--path", required=True)
    def _read_file(a):
        repo_root = Path(__file__).resolve().parent.parent
        target = (repo_root / a.path).resolve()
        if not str(target).startswith(str(repo_root)):
            raise fileops.ActionError("path outside repo")
        if not target.exists():
            raise fileops.ActionError(f"file not found: {a.path}")
        return {"path": a.path, "content": target.read_text(encoding="utf-8")}
    p.set_defaults(_run=_read_file)

    return parser


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
