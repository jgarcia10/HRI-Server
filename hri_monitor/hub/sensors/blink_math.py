"""Pure EAR + weighted blink-rate logic, ported from hri_server.py blink_loop()."""
import numpy as np

LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]


def eye_aspect_ratio(eye: np.ndarray) -> float:
    a = np.linalg.norm(eye[1] - eye[5])
    b = np.linalg.norm(eye[2] - eye[4])
    c = np.linalg.norm(eye[0] - eye[3])
    return float((a + b) / (2.0 * c)) if c != 0 else 0.0


class BlinkRate:
    """Weighted blinks/min: 0.1*cumulative + 0.7*sliding(window) + 0.2*instant."""

    def __init__(self, ear_threshold=0.25, consecutive=3, window=5.0):
        self.ear_threshold = ear_threshold
        self.consecutive = consecutive
        self.window = window
        self.blink_count = 0
        self._frames_closed = 0
        self._was_closed = False
        self._start = None
        self._sliding: list[float] = []
        self._last_blink_t = None
        self._instant = 0.0

    def update(self, ear: float, t: float) -> float:
        if self._start is None:
            self._start = t
        if ear < self.ear_threshold:
            self._frames_closed += 1
        else:
            if self._frames_closed >= self.consecutive and not self._was_closed:
                self.blink_count += 1
                self._sliding.append(t)
                if self._last_blink_t is not None:
                    dt = t - self._last_blink_t
                    self._instant = 60.0 / dt if dt > 0 else 0.0
                self._last_blink_t = t
                self._was_closed = True
            self._frames_closed = 0
            self._was_closed = False
        elapsed_min = (t - self._start) / 60.0
        cumulative = self.blink_count / elapsed_min if elapsed_min > 0 else 0.0
        self._sliding = [ts for ts in self._sliding if t - ts <= self.window]
        sliding = len(self._sliding) * (60.0 / self.window)
        return 0.1 * cumulative + 0.7 * sliding + 0.2 * self._instant
