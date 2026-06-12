import numpy as np

from hub.bus import MessageBus
from hub.frames import FrameStore


def test_frame_store_returns_jpeg_of_latest_frame():
    bus = MessageBus()
    store = FrameStore(bus, {"thermal": "thermal.frame"})
    assert store.has("thermal") and not store.has("nope")
    assert store.jpeg("thermal") is None
    bus.publish("thermal.frame", {"frame": np.zeros((10, 10, 3), dtype=np.uint8)})
    jpg = store.jpeg("thermal")
    assert jpg is not None and jpg[:2] == b"\xff\xd8"  # JPEG magic bytes
