import struct

from hub.sensors.shimmer_decode import clock_wait_for_rate, decode_frame, HeartRate


def make_frame(ppg_raw, gsr_raw, t=1000):
    t0, t1, t2 = t & 0xFF, (t >> 8) & 0xFF, (t >> 16) & 0xFF
    return bytes([0x00, t0, t1, t2]) + struct.pack("HH", ppg_raw, gsr_raw)


def test_decode_frame_gsr_ppg():
    gsr_raw = 2000  # range 0, adc ~2000
    ppg_raw = 2048
    s = decode_frame(make_frame(ppg_raw, gsr_raw))
    assert s["timestamp"] == 1000
    assert abs(s["ppg"] - 2048 * (3000.0 / 4095.0)) < 0.01
    assert s["gsr"] > 0


def test_decode_frame_each_gsr_range_uses_right_rf():
    rfs = [40.2, 287.0, 1000.0, 3300.0]
    for rng, rf in enumerate(rfs):
        gsr_raw = (rng << 14) | 1000
        s = decode_frame(make_frame(2048, gsr_raw))
        adc = 1000 * (3.0 / 4095.0)
        ohm = rf / ((adc / 0.5) - 1.0)
        assert abs(s["gsr"] - 1_000_000.0 / ohm) < 1.0


def test_clock_wait_for_rate():
    assert clock_wait_for_rate(200) == int((2 << 14) / 200)


def test_heart_rate_from_periodic_peaks():
    hr = HeartRate(fs=200)
    import math
    bpm = None
    for i in range(200 * 6):
        v = 1500 + 400 * math.sin(2 * math.pi * 1.2 * i / 200.0)
        out = hr.update(v, i / 200.0)
        if out:
            bpm, _hrv = out
    assert bpm is not None and 60 < bpm < 84
