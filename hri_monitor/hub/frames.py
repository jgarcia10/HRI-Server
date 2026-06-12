import threading

import cv2


class FrameStore:
    """Keeps the latest raw frame per named feed and encodes JPEG on demand.

    feeds maps a public feed name to a bus topic whose payload is
    {"frame": np.ndarray}, e.g. {"thermal": "thermal.frame"}. Frames are held
    by reference: producers must emit a fresh array per frame, and subscribers
    must copy a frame before mutating it.
    """

    def __init__(self, bus, feeds: dict):
        self._feeds = dict(feeds)
        self._frames = {}
        self._lock = threading.Lock()
        for feed, topic in self._feeds.items():
            bus.subscribe(topic, self._make_handler(feed))

    def _make_handler(self, feed: str):
        def handler(message):
            with self._lock:
                self._frames[feed] = message["data"]["frame"]
        return handler

    def has(self, feed: str) -> bool:
        return feed in self._feeds

    def jpeg(self, feed: str) -> bytes | None:
        with self._lock:
            frame = self._frames.get(feed)
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None
