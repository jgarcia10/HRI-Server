import io

import numpy as np

from hub.sensors.thermal_codec import encode_message, read_message


def test_encode_read_roundtrip():
    frame = np.arange(240 * 320 * 3, dtype=np.uint8).reshape((240, 320, 3))
    temps = {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5}
    blob = encode_message(temps, frame)
    reader = io.BytesIO(blob)
    got_temps, got_frame = read_message(reader)
    assert got_temps == temps
    assert got_frame.shape == frame.shape
    assert np.array_equal(got_frame, frame)


def test_read_message_returns_none_on_eof():
    assert read_message(io.BytesIO(b"")) is None


def test_read_two_messages_in_sequence():
    f = np.zeros((2, 2, 3), dtype=np.uint8)
    stream = io.BytesIO(encode_message({"nose": 30.0}, f) + encode_message({"nose": 31.0}, f))
    m1 = read_message(stream)
    m2 = read_message(stream)
    assert m1[0]["nose"] == 30.0 and m2[0]["nose"] == 31.0
