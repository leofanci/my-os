"""chat_session.py — one persistent Claude Code session for the dashboard run.

Runs `claude` in stream-json mode loading ONLY the Bash tool, restricted to the
osctl CLI, so the agent can ONLY mutate state via `python -m dashboard.osctl`.
The harness is run lean (no MCP, skills, hooks, CLAUDE.md, or default system
prompt) to keep per-turn context small — see _base_cmd for the flags. Parses
stream-json events into simple (kind, payload) tuples for the SSE layer.

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


# Chat agent runs osctl only — no file exploration needed or wanted.
# Only the Bash tool is loaded (--tools Bash), and it is restricted to osctl.
# Both `python3` (what the model actually invokes on macOS) and bare `python`
# are allowed so the command auto-approves without a permission prompt. Passed
# as separate --allowedTools args (see _base_cmd) — do not join with spaces.
ALLOWED_TOOLS = [
    "Bash(python3 -m dashboard.osctl:*)",
    "Bash(python -m dashboard.osctl:*)",
]

# The dashboard chat agent ALWAYS runs on this model — independent of the user's
# interactive `/model` default, which only affects the full terminal. Change it
# here (e.g. "haiku" for speed, "opus" for depth) if ever needed.
CHAT_MODEL = "sonnet"


class ChatSession:
    def __init__(self, repo_dir, rail, claude_bin="claude", session_id=None, model=CHAT_MODEL):
        self.repo_dir = repo_dir
        self.rail = rail
        self.claude_bin = claude_bin
        self.model = model
        self.session_id = session_id or str(uuid.uuid4())
        self._started = False
        self._proc = None  # the in-flight `claude -p` turn, if any

    def _base_cmd(self):
        # Lean per-turn context: the dashboard chat only needs Bash→osctl, so we
        # strip everything the full Claude Code harness would otherwise load each
        # turn (≈24k→≈4k tokens). Measured levers, biggest first:
        #   --system-prompt        REPLACES Claude Code's default prompt with our
        #                          self-contained RAIL (was --append-system-prompt,
        #                          which kept the ~10k default on top).
        #   --tools Bash           load ONLY the Bash tool schema (no Read/Edit/…).
        #   --strict-mcp-config    no --mcp-config given ⇒ zero MCP servers/tools.
        #   --disable-slash-commands  skip all skills.
        #   --setting-sources ""   skip user/project/local settings ⇒ no hooks,
        #                          no auto-memory, no CLAUDE.md injection.
        # NB: do NOT use --bare here — it forces ANTHROPIC_API_KEY and ignores the
        # subscription OAuth login. The flags above keep OAuth intact.
        cmd = [self.claude_bin, "-p",
               "--output-format", "stream-json",
               "--include-partial-messages",
               "--verbose",
               "--model", self.model,  # see CHAT_MODEL — chat is always Sonnet
               "--system-prompt", self.rail,
               "--tools", "Bash",
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

    def ask(self, text):
        """Run one turn; yield (kind, payload) events. Each turn is its own
        `claude -p` invocation, resumed by session id so context persists."""
        proc = subprocess.Popen(
            self._base_cmd(), cwd=self.repo_dir,
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
        finally:
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            self._proc = None

    def close(self):
        """Terminate any in-flight turn. Safe to call when idle (no-op)."""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        self._proc = None
