import numpy as np

from hub.sensors.blink_math import eye_aspect_ratio, BlinkRate


def test_ear_open_vs_closed():
    open_eye = np.array([(0, 0), (1, 2), (2, 2), (3, 0), (2, -2), (1, -2)], dtype=float)
    closed_eye = np.array([(0, 0), (1, 0.1), (2, 0.1), (3, 0), (2, -0.1), (1, -0.1)], dtype=float)
    assert eye_aspect_ratio(open_eye) > eye_aspect_ratio(closed_eye)


def test_blink_rate_counts_and_weights():
    br = BlinkRate(ear_threshold=0.25, consecutive=3, window=5.0)
    t = 0.0
    for _ in range(3):
        br.update(0.1, t); t += 0.03
    rate = br.update(0.4, t)  # transition open registers the blink
    assert br.blink_count == 1
    assert rate >= 0.0
