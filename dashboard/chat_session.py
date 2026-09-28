"""chat_session.py — one Claude Code session per saved dashboard chat.

Runs `claude` in stream-json mode. Bash is restricted to the osctl CLI, so the
agent can ONLY mutate GTM state via `python -m dashboard.osctl`; Read is always
available for myOS. Glob/Grep and linked-folder access are loaded only when a
turn explicitly needs file-search fallback. TokenSave retrieval happens once in
the server before the model starts, so the agent cannot skip or repeat it. No
MCP, no default system prompt — see _base_cmd for the flags. Parses stream-json
events into simple (kind, payload) tuples for the SSE layer.

The event field paths below were confirmed against claude 2.1.179
(`--output-format stream-json --include-partial-messages --verbose`): text
deltas arrive as stream_event/content_block_delta/text_delta, tool starts as
stream_event/content_block_start/tool_use, and the turn ends with a top-level
`result` line. A plain-text stdin turn (no positional prompt) is accepted.
"""
import json
import re
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


# Hostnames typed by the user. Bare names need a real-looking TLD so file names
# like notes.md / app.py are not mistaken for hosts.
_URL_HOST_RE = re.compile(r"https?://([a-z0-9.-]+\.[a-z]{2,})", re.I)
_BARE_HOST_RE = re.compile(r"(?<![\w@/.-])((?:[a-z0-9-]+\.)+[a-z]{2,})(?![\w.-])", re.I)
_FILE_EXTS = frozenset({
    "md", "py", "js", "ts", "json", "txt", "csv", "html", "css", "sh", "yml",
    "yaml", "toml", "lock", "log", "sql", "png", "jpg", "jpeg", "gif", "pdf",
})


def user_web_domains(text):
    """Hosts the user explicitly named in their message (lowercased, www. stripped)."""
    text = (text or "")[:20000]  # bodies may be huge; hosts are typed near the top
    hosts = {h.lower() for h in _URL_HOST_RE.findall(text)}
    for h in _BARE_HOST_RE.findall(text):
        if h.rsplit(".", 1)[-1].lower() not in _FILE_EXTS:
            hosts.add(h.lower())
    return sorted({h[4:] if h.startswith("www.") else h for h in hosts})


def web_fetch_rules(domains):
    return [r for d in domains for r in (f"WebFetch(domain:{d})", f"WebFetch(domain:www.{d})")]


# Mutations go through osctl ONLY (Write/Edit are never loaded, so the
# authored-files-are-truth invariant holds). Permissions are assembled per turn:
# linked-folder and TokenSave permissions do not exist on ordinary chat turns.
# Passed as separate --allowedTools args — do not join with spaces.
BASE_ALLOWED_TOOLS = [
    "Bash(python3 -m dashboard.osctl:*)",
    "Bash(python -m dashboard.osctl:*)",
    "Read",
]
APP_ALLOWED_TOOLS = [
    "Glob",
    "Grep",
]
# WebFetch is never granted broadly: a fetched page (or a linked app file) can
# carry injected instructions telling the agent to fetch attacker.com/?d=<data>.
# Only hosts the user typed in the message are fetchable (web_fetch_rules);
# WebSearch stays open. In -p mode any other fetch is denied, not prompted.
WEB_ALLOWED_TOOLS = [
    "WebSearch",
]
# Secret-looking files stay unreadable even inside the repo or a linked app
# folder (Grep/Glob honor Read deny rules too). Verified against claude 2.x:
# "**/x" covers the repo; a linked --add-dir needs its own "//abs/**/x" rule.
SECRET_FILE_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", ".npmrc", ".netrc",
    "credentials*.json", "secrets.*", "id_rsa*", "id_ed25519*",
    ".auth-token",  # dashboard login token (server.TOKEN_FILE)
]
# Tools loaded EVERY turn. Skills are NOT loaded via the Skill tool — that costs
# ~4k tok of discovery (35 descriptions, incl. useless built-ins) just to let the
# model pick one. Instead the server routes to the ONE relevant skill and injects
# its SKILL.md into the prompt (see server._route_skill) — no discovery overhead.
BASE_TOOLS = ["Bash", "Read"]
# App-code discovery is progressive: these schemas are present only for a code
# question whose active GTM project has a linked folder. Neither tool modifies files.
APP_TOOLS = ["Glob", "Grep"]
# WebSearch/WebFetch are added only on turns whose request needs live research
# (server._needs_web) — their schemas are small but off by default per the
# token-lean policy.
WEB_TOOLS = ["WebSearch", "WebFetch"]

# No turn cap: a chat persists via --resume until the user deletes it.
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

    @classmethod
    def restore(cls, repo_dir, rail, rec, **kw):
        """Rebuild a saved chat (chat_store record) so the next turn --resumes it."""
        sess = cls(repo_dir=repo_dir, rail=rail, session_id=rec["id"], **kw)
        sess._started = bool(rec.get("started"))
        sess._turn_count = int(rec.get("turn_count") or 0)
        sess._last_skill = rec.get("last_skill")
        sess._skill_explicit = bool(rec.get("skill_explicit"))
        return sess

    def is_fresh(self):
        """True before the first turn of this session id (no --resume yet)."""
        return not self._started

    def session_meta(self):
        return {
            "session_id": self.session_id,
            "turn_count": self._turn_count,
            "fresh": self.is_fresh(),
        }

    def _base_cmd(self, with_web=False, model=None, workspace_dir=None,
                  file_search_mode=False, web_domains=()):
        # Lean per-turn flags. Skills are NEVER discovered here (the server injects
        # the routed skill's body into the prompt instead), so we always pass
        # --disable-slash-commands + --setting-sources "" — zero skill-discovery
        # tokens, no leaked built-in commands.
        #   --system-prompt        REPLACES Claude Code's default prompt with RAIL.
        #   --tools Bash Read [Glob Grep] [WebSearch WebFetch]  app discovery is
        #                          loaded only for a linked workspace; mutations
        #                          stay osctl-only. Web tools are likewise opt-in.
        #   --add-dir             grants file-tool access to that one linked app
        #                          folder for the current turn; no eager read.
        #   --strict-mcp-config    no --mcp-config given ⇒ zero MCP servers/tools.
        #   --model                per-turn (server tiers haiku→sonnet).
        # Changing model/tools per turn is safe across --resume: the session is
        # restored from disk by id and context is preserved (verified). Do NOT use
        # --bare — it changes auth behavior.
        tools = (list(BASE_TOOLS)
                 + (APP_TOOLS if workspace_dir and file_search_mode else [])
                 + (WEB_TOOLS if with_web else []))
        allowed_tools = (list(BASE_ALLOWED_TOOLS)
                         + (APP_ALLOWED_TOOLS
                            if workspace_dir and file_search_mode else [])
                         + (WEB_ALLOWED_TOOLS if with_web else [])
                         + (web_fetch_rules(web_domains) if with_web else []))
        denied = [f"Read(**/{g})" for g in SECRET_FILE_GLOBS]
        if workspace_dir and file_search_mode:
            denied += [f"Read(/{workspace_dir}/**/{g})" for g in SECRET_FILE_GLOBS]
        cmd = [self.claude_bin, "-p",
               "--output-format", "stream-json",
               "--include-partial-messages",
               "--verbose",
               "--model", model or self.model,
               "--system-prompt", self.rail,
               "--tools", *tools,
               "--allowedTools", *allowed_tools,
               "--disallowedTools", *denied,
               "--strict-mcp-config",
               "--disable-slash-commands",
               "--setting-sources", "",
               "--restricted",
               "--permission-mode", "default"]
        if workspace_dir and file_search_mode:
            cmd += ["--add-dir", str(workspace_dir)]
        if self._started:
            cmd += ["--resume", self.session_id]
        else:
            cmd += ["--session-id", self.session_id]
        return cmd

    def ask(self, text, with_web=False, model=None, workspace_dir=None,
            file_search_mode=False, web_domains=()):
        """Run one turn; yield (kind, payload) events. Each turn is its own
        `claude -p` invocation, resumed by session id so context persists.
        `with_web` adds the WebSearch/WebFetch tools for this turn;
        `workspace_dir` plus `file_search_mode` grants read-only access to one
        linked app and adds Glob/Grep only when fallback discovery is warranted;
        `model` overrides the default for this turn (the server tiers per turn —
        see server._needs_web / _pick_model). Any routed skill is already
        injected into `text` by the server. Server injects full snapshot + skill
        body on fresh session start only (no turn cap — session never auto-resets)."""
        proc = subprocess.Popen(
            self._base_cmd(with_web, model, workspace_dir, file_search_mode,
                           web_domains),
            cwd=self.repo_dir,
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
