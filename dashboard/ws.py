"""ws.py — minimal RFC 6455 WebSocket framing for the stdlib server.

Pure functions only (no sockets), so they are fully unit-testable. The server's
/ws/terminal handler uses these to talk to the browser's xterm.js client.
"""
import base64
import hashlib
import struct

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


def accept_key(client_key):
    digest = hashlib.sha1((client_key + _GUID).encode()).digest()
    return base64.b64encode(digest).decode()


def encode_frame(payload, opcode=OP_TEXT):
    b0 = 0x80 | (opcode & 0x0F)  # FIN=1
    n = len(payload)
    if n < 126:
        header = struct.pack("!BB", b0, n)
    elif n < (1 << 16):
        header = struct.pack("!BBH", b0, 126, n)
    else:
        header = struct.pack("!BBQ", b0, 127, n)
    return header + payload


def decode_frame(buf, *, max_payload=None, require_masked=False):
    """Decode one frame from the front of buf. Returns (opcode, payload, consumed)
    or (None, b"", 0) if a full frame is not yet present."""
    if len(buf) < 2:
        return (None, b"", 0)
    b0, b1 = buf[0], buf[1]
    fin = bool(b0 & 0x80)
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    if b0 & 0x70:
        raise ValueError("unsupported WebSocket extension bits")
    if not fin:
        raise ValueError("fragmented WebSocket frames are unsupported")
    if require_masked and not masked:
        raise ValueError("client WebSocket frames must be masked")
    if opcode not in {OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG}:
        raise ValueError("unsupported WebSocket opcode")
    length = b1 & 0x7F
    idx = 2
    if length == 126:
        if len(buf) < idx + 2:
            return (None, b"", 0)
        length = struct.unpack("!H", buf[idx:idx + 2])[0]
        idx += 2
    elif length == 127:
        if len(buf) < idx + 8:
            return (None, b"", 0)
        length = struct.unpack("!Q", buf[idx:idx + 8])[0]
        idx += 8
    if opcode >= 0x8 and length > 125:
        raise ValueError("oversized WebSocket control frame")
    if max_payload is not None and length > max_payload:
        raise ValueError("WebSocket payload too large")
    if masked:
        if len(buf) < idx + 4:
            return (None, b"", 0)
        mask = buf[idx:idx + 4]
        idx += 4
    if len(buf) < idx + length:
        return (None, b"", 0)
    data = buf[idx:idx + length]
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return (opcode, data, idx + length)
