"""chat_session.py — one persistent Claude Code session for the dashboard run.

Runs `claude` in stream-json mode with a permission allowlist limited to the
osctl CLI + read tools, so the agent can ONLY mutate state via
`python -m dashboard.osctl`. Parses stream-json events into simple
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


# Allowlist: the agent may run osctl + read-only tools, nothing else.
ALLOWED_TOOLS = "Bash(python -m dashboard.osctl:*) Read Grep Glob"
DISALLOWED_TOOLS = "Write Edit"

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
        cmd = [self.claude_bin, "-p",
               "--output-format", "stream-json",
               "--include-partial-messages",
               "--verbose",
               "--model", self.model,  # see CHAT_MODEL — chat is always Sonnet
               "--add-dir", self.repo_dir,
               "--append-system-prompt", self.rail,
               "--allowedTools", ALLOWED_TOOLS,
               "--disallowedTools", DISALLOWED_TOOLS,
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
