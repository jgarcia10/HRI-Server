"""Pure Shimmer GSR+/PPG decode + HR/HRV — no hardware, fully unit-tested.
Ported from hri_server.py data_read_loop()."""
import struct

FRAMESIZE = 8
_RF = [40.2, 287.0, 1000.0, 3300.0]  # feedback resistor per GSR range


def clock_wait_for_rate(sampling_rate: int) -> int:
    return int((2 << 14) / sampling_rate)


def decode_frame(data: bytes) -> dict:
    """Decode one 8-byte Shimmer frame → {timestamp, gsr (µS), ppg (mV)}."""
    t0, t1, t2 = data[1], data[2], data[3]
    timestamp = t0 + t1 * 256 + t2 * 65536
    ppg_raw, gsr_raw = struct.unpack("HH", data[4:8])
    rng = (gsr_raw >> 14) & 0x03
    rf = _RF[rng]
    gsr_volts = (gsr_raw & 0x3FFF) * (3.0 / 4095.0)
    gsr_ohm = rf / ((gsr_volts / 0.5) - 1.0)
    gsr_muS = 1_000_000.0 / gsr_ohm
    ppg_mv = ppg_raw * (3000.0 / 4095.0)
    return {"timestamp": timestamp, "gsr": round(gsr_muS, 3), "ppg": round(ppg_mv, 3)}


class HeartRate:
    """Rolling PPG peak detector → (bpm, rmssd_ms). Emits once enough beats seen."""

    def __init__(self, fs: int, window_s: float = 10.0):
        self.fs = fs
        self.window_s = window_s
        self._buf: list[tuple[float, float]] = []  # (t, v)
        self._peaks: list[float] = []  # peak times

    def update(self, ppg: float, t: float):
        self._buf.append((t, ppg))
        self._buf = [(bt, bv) for bt, bv in self._buf if t - bt <= self.window_s]
        if len(self._buf) < 5:
            return None
        vals = [v for _, v in self._buf]
        mean = sum(vals) / len(vals)
        a, b, c = self._buf[-3], self._buf[-2], self._buf[-1]
        if b[1] > a[1] and b[1] >= c[1] and b[1] > mean:
            if not self._peaks or b[0] - self._peaks[-1] > 0.33:  # refractory 0.33s (<180bpm)
                self._peaks.append(b[0])
        self._peaks = [pt for pt in self._peaks if t - pt <= self.window_s]
        if len(self._peaks) < 3:
            return None
        intervals = [self._peaks[i + 1] - self._peaks[i] for i in range(len(self._peaks) - 1)]
        mean_ibi = sum(intervals) / len(intervals)
        if mean_ibi <= 0:
            return None
        bpm = 60.0 / mean_ibi
        diffs = [(intervals[i + 1] - intervals[i]) * 1000.0 for i in range(len(intervals) - 1)]
        rmssd = (sum(d * d for d in diffs) / len(diffs)) ** 0.5 if diffs else 0.0
        return round(bpm, 1), round(rmssd, 1)
