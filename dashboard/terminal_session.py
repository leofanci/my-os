"""terminal_session.py — a claude process attached to a PTY.

The bottom integrated terminal runs full (unrestricted) `claude` here; bytes are
bridged to the browser's xterm.js over the /ws/terminal WebSocket. The chat
agent's osctl guard rail does NOT apply to this surface — it is the full-trust
power terminal.
"""
import fcntl
import os
import pty
import signal
import struct
import termios
import threading


class TerminalSession:
    def __init__(self, cmd, cwd):
        self.cmd = cmd
        self.cwd = cwd
        self.pid = None
        self.fd = None
        self._reader = None
        self._alive = False

    def start(self, on_output):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # child
            try:
                os.chdir(self.cwd)
                os.execvp(self.cmd[0], self.cmd)
            except Exception:
                os._exit(1)
        self._alive = True

        def pump():
            while self._alive:
                try:
                    data = os.read(self.fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                on_output(data)
            self._alive = False

        self._reader = threading.Thread(target=pump, daemon=True)
        self._reader.start()

    def write(self, data):
        if self.fd is not None:
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def resize(self, cols, rows):
        if self.fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
            if self.pid:
                os.kill(self.pid, signal.SIGWINCH)
        except OSError:
            pass

    def close(self):
        self._alive = False
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except OSError:
                pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
