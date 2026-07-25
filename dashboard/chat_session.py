"""chat_session.py — one persistent Claude Code session for the dashboard run.

Runs `claude` in stream-json mode. Tools loaded: Bash (restricted to the osctl
CLI, so the agent can ONLY mutate state via `python -m dashboard.osctl`), Read
(read-only — safe), and Skill (so the agent can invoke the OS skills in
.claude/skills on demand via progressive disclosure). No MCP, no default system
prompt — see _base_cmd for the flags. Parses stream-json events into simple
(kind, payload) tuples for the SSE layer.

The event field paths below were confirmed against claude 2.1.179
(`--output-format stream-json --include-partial-messages --verbose`): text
deltas arrive as stream_event/content_block_delta/text_delta, tool starts as
stream_event/content_block_start/tool_use, and the turn ends with a top-level
`result` line. A plain-text stdin turn (no positional prompt) is accepted.
"""
import json
import subprocess
import uuid


def parse_event(obj):
    """Map one decoded stream-json line to (kind, payload). See module docstring."""
    t = obj.get("type")
    if t == "stream_event":
        ev = obj.get("event", {})
        et = ev.get("type")
        if et == "content_block_delta":
            delta = ev.get("delta", {})
            if delta.get("type") == "text_delta":
                return ("delta", delta.get("text", ""))
        elif et == "content_block_start":
            block = ev.get("content_block", {})
            if block.get("type") == "tool_use":
                return ("tool", block.get("name", ""))
    elif t == "result":
        return ("done", {"result": obj.get("result"), "subtype": obj.get("subtype")})
    return (None, None)


# Mutations go through osctl ONLY (Write/Edit are never loaded, so the
# authored-files-are-truth invariant holds). Read is read-only/safe: it lets the
# agent (and skills) open exact paths on demand. Both `python3` (what the model
# invokes on macOS) and bare `python` are allowed so osctl auto-approves without
# a prompt. Passed as separate --allowedTools args — do not join with spaces.
ALLOWED_TOOLS = [
    "Bash(python3 -m dashboard.osctl:*)",
    "Bash(python -m dashboard.osctl:*)",
    "Read",
    "WebSearch",
    "WebFetch",
]
# Tools loaded EVERY turn. Skills are NOT loaded via the Skill tool — that costs
# ~4k tok of discovery (35 descriptions, incl. useless built-ins) just to let the
# model pick one. Instead the server routes to the ONE relevant skill and injects
# its SKILL.md into the prompt (see server._route_skill) — no discovery overhead.
BASE_TOOLS = ["Bash", "Read"]
# WebSearch/WebFetch are added only on turns whose request needs live research
# (server._needs_web) — their schemas are small but off by default per the
# token-lean policy.
WEB_TOOLS = ["WebSearch", "WebFetch"]

# No turn cap: session persists via --resume for the life of the dashboard run.
# Full state snapshot + skill body inject on session start only (server); resume
# turns rely on Claude session history + osctl on demand.

# Default model for ordinary turns. The server escalates to a stronger model
# (ESCALATED_MODEL) on skill/web/strategic turns; mechanical turns (reads,
# mutations, chit-chat) stay on the cheap one — this is what actually keeps
# rate-limit-window consumption down, since a cheaper model costs less quota
# per token than caching can reliably claw back. See server._pick_model.
CHAT_MODEL = "haiku"
ESCALATED_MODEL = "sonnet"


class ChatSession:
    def __init__(self, repo_dir, rail, claude_bin="claude", session_id=None, model=CHAT_MODEL):
        self.repo_dir = repo_dir
        self.rail = rail
        self.claude_bin = claude_bin
        self.model = model
        self.session_id = session_id or str(uuid.uuid4())
        self._started = False
        self._proc = None  # the in-flight `claude -p` turn, if any
        self._turn_count = 0
        self._last_skill = None  # last routed skill (server); skip re-injecting body
        self._skill_explicit = False  # True when user tagged @/skill (Sonnet gate)
        self._pending_skill = None
        self._pending_skill_explicit = False

    def is_fresh(self):
        """True before the first turn of this session id (no --resume yet)."""
        return not self._started

    def session_meta(self):
        return {
            "session_id": self.session_id,
            "turn_count": self._turn_count,
            "fresh": self.is_fresh(),
        }

    def _base_cmd(self, with_web=False, model=None):
        # Lean per-turn flags. Skills are NEVER discovered here (the server injects
        # the routed skill's body into the prompt instead), so we always pass
        # --disable-slash-commands + --setting-sources "" — zero skill-discovery
        # tokens, no leaked built-in commands.
        #   --system-prompt        REPLACES Claude Code's default prompt with RAIL.
        #   --tools Bash Read [WebSearch WebFetch]  only these schemas (no Write/
        #                          Edit/Glob/Grep) — mutations stay osctl-only. Web
        #                          tools added only when with_web.
        #   --strict-mcp-config    no --mcp-config given ⇒ zero MCP servers/tools.
        #   --model                per-turn (server tiers haiku→sonnet).
        # Changing model/tools per turn is safe across --resume: the session is
        # restored from disk by id and context is preserved (verified). Do NOT use
        # --bare — it changes auth behavior.
        tools = list(BASE_TOOLS) + (WEB_TOOLS if with_web else [])
        cmd = [self.claude_bin, "-p",
               "--output-format", "stream-json",
               "--include-partial-messages",
               "--verbose",
               "--model", model or self.model,
               "--system-prompt", self.rail,
               "--tools", *tools,
               "--allowedTools", *ALLOWED_TOOLS,
               "--strict-mcp-config",
               "--disable-slash-commands",
               "--setting-sources", "",
               "--permission-mode", "default"]
        if self._started:
            cmd += ["--resume", self.session_id]
        else:
            cmd += ["--session-id", self.session_id]
        return cmd

    def ask(self, text, with_web=False, model=None):
        """Run one turn; yield (kind, payload) events. Each turn is its own
        `claude -p` invocation, resumed by session id so context persists.
        `with_web` adds the WebSearch/WebFetch tools for this turn; `model`
        overrides the default for this turn (the server tiers per turn — see
        server._needs_web / _pick_model). Any routed skill is already injected
        into `text` by the server. Server injects full snapshot + skill body on
        fresh session start only (no turn cap — session never auto-resets)."""
        proc = subprocess.Popen(
            self._base_cmd(with_web, model), cwd=self.repo_dir,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        self._started = True
        self._proc = proc
        proc.stdin.write(text + "\n")
        proc.stdin.close()
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind, payload = parse_event(obj)
                if kind:
                    yield (kind, payload)
            proc.wait()
            if proc.returncode not in (0, None):
                yield ("error", (proc.stderr.read() or "")[:500])
            else:
                self._turn_count += 1
                if self._pending_skill:
                    self._last_skill = self._pending_skill
                    self._skill_explicit = self._pending_skill_explicit
                self._pending_skill = None
                self._pending_skill_explicit = False
        finally:
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            self._proc = None

    def note_skill(self, skill, explicit=False):
        """Record routed skill for this turn (applied after successful completion)."""
        self._pending_skill = skill
        self._pending_skill_explicit = bool(explicit and skill)

    def close(self):
        """Terminate any in-flight turn. Safe to call when idle (no-op)."""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        self._proc = None
