import unittest
import dashboard.ws as ws


class WS(unittest.TestCase):
    def test_accept_key_rfc_example(self):
        # RFC 6455 §1.3 worked example
        self.assertEqual(ws.accept_key("dGhlIHNhbXBsZSBub25jZQ=="),
                         "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_encode_small_text(self):
        frame = ws.encode_frame(b"hi", opcode=0x1)
        self.assertEqual(frame[0], 0x81)        # FIN + text
        self.assertEqual(frame[1], 0x02)        # unmasked, len 2
        self.assertEqual(frame[2:], b"hi")

    def test_decode_masked_client_frame_roundtrip(self):
        # Build a masked client text frame for "hi"
        mask = bytes([1, 2, 3, 4])
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(b"hi"))
        buf = bytes([0x81, 0x82]) + mask + masked
        opcode, payload, consumed = ws.decode_frame(buf)
        self.assertEqual(opcode, 0x1)
        self.assertEqual(payload, b"hi")
        self.assertEqual(consumed, len(buf))

    def test_decode_incomplete_returns_none(self):
        self.assertEqual(ws.decode_frame(b"\x81"), (None, b"", 0))


if __name__ == "__main__":
    unittest.main()
