import os, threading, unittest
import dashboard.terminal_session as ts


class Term(unittest.TestCase):
    def test_echo_roundtrip(self):
        got = bytearray()
        done = threading.Event()

        def on_output(chunk):
            got.extend(chunk)
            if b"PONG" in got:
                done.set()

        # `cat` echoes stdin back to its PTY stdout
        sess = ts.TerminalSession(cmd=["cat"], cwd=".")
        sess.start(on_output)
        sess.write(b"PONG\n")
        done.wait(timeout=5)
        sess.close()
        self.assertIn(b"PONG", bytes(got))

    def test_terminal_keeps_the_users_umask(self):
        # The server runs owner-only (umask 077); the full-trust terminal is the
        # user's own shell, so files made there (npm, git clones) stay normal.
        got = bytearray()
        done = threading.Event()

        def on_output(chunk):
            got.extend(chunk)
            if b"\n" in got:
                done.set()
        old = os.umask(0o077)
        try:
            ts.USER_UMASK = 0o022
            sess = ts.TerminalSession(cmd=["sh", "-c", "umask"], cwd=".")
            sess.start(on_output)
            done.wait(timeout=5)
            sess.close()
        finally:
            os.umask(old)
            ts.USER_UMASK = None
        self.assertIn(b"0022", bytes(got))

    def test_resize_no_crash(self):
        sess = ts.TerminalSession(cmd=["cat"], cwd=".")
        sess.start(lambda c: None)
        sess.resize(100, 40)   # must not raise
        sess.close()


if __name__ == "__main__":
    unittest.main()
