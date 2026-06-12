import logging
import threading
import time
from collections import defaultdict

log = logging.getLogger(__name__)


class MessageBus:
    """Thread-safe in-process pub/sub. Subscribe to '*' to receive everything.

    Messages are dicts: {"topic": str, "ts": float, "data": Any}. Callbacks run
    on the publisher's thread and must not raise (failures are logged and
    isolated so one bad subscriber cannot break the others).
    """

    def __init__(self):
        self._subs: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback) -> None:
        with self._lock:
            self._subs[topic].append(callback)

    def unsubscribe(self, topic: str, callback) -> None:
        with self._lock:
            if callback in self._subs.get(topic, []):
                self._subs[topic].remove(callback)

    def publish(self, topic: str, data) -> None:
        message = {"topic": topic, "ts": time.time(), "data": data}
        with self._lock:
            callbacks = list(self._subs.get(topic, [])) + list(self._subs.get("*", []))
        for callback in callbacks:
            try:
                callback(message)
            except Exception:
                log.exception("Bus subscriber failed for topic %s", topic)
