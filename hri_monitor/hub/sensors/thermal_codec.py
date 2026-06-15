"""Length-prefixed frame+temps messages between the thermal worker subprocess
and the hub-side proxy. Format: [4B meta-len][meta JSON][raw uint8 BGR bytes].
meta = {"temps": {...}, "h": int, "w": int}."""
import json
import struct

import numpy as np


def encode_message(temps: dict, frame: np.ndarray) -> bytes:
    h, w = frame.shape[0], frame.shape[1]
    meta = json.dumps({"temps": temps, "h": h, "w": w}).encode("utf-8")
    body = frame.astype(np.uint8).tobytes()
    return struct.pack(">I", len(meta)) + meta + body


def _read_exactly(reader, n: int) -> bytes | None:
    chunks = []
    got = 0
    while got < n:
        chunk = reader.read(n - got)
        if not chunk:
            return None
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def read_message(reader):
    """Read one message from a binary reader -> (temps, frame) or None at EOF."""
    header = _read_exactly(reader, 4)
    if header is None:
        return None
    (meta_len,) = struct.unpack(">I", header)
    meta_bytes = _read_exactly(reader, meta_len)
    if meta_bytes is None:
        return None
    meta = json.loads(meta_bytes.decode("utf-8"))
    h, w = meta["h"], meta["w"]
    body = _read_exactly(reader, h * w * 3)
    if body is None:
        return None
    frame = np.frombuffer(body, dtype=np.uint8).reshape((h, w, 3))
    return meta["temps"], frame
