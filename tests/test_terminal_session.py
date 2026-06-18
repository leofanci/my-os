import threading, unittest
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

    def test_resize_no_crash(self):
        sess = ts.TerminalSession(cmd=["cat"], cwd=".")
        sess.start(lambda c: None)
        sess.resize(100, 40)   # must not raise
        sess.close()


if __name__ == "__main__":
    unittest.main()
