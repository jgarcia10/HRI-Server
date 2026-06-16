"""Per-recording descriptive stats computed from a tidy CSV. Single-pass
(Welford) so large multi-minute recordings summarise in O(1) memory per signal.
Read-only: never mutates the recording. Inferential condition-comparison lives
in the later Analysis milestone."""
import csv
import math
import os


class _Acc:
    __slots__ = ("count", "mean", "_m2", "min", "max")

    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self._m2 = 0.0
        self.min = math.inf
        self.max = -math.inf

    def add(self, x: float):
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self._m2 += delta * (x - self.mean)
        if x < self.min:
            self.min = x
        if x > self.max:
            self.max = x

    def result(self) -> dict:
        # Full precision here; the UI formats for display.
        std = math.sqrt(self._m2 / self.count) if self.count > 0 else 0.0
        return {"count": self.count, "mean": self.mean,
                "min": self.min, "max": self.max, "std": std}


def summarize_csv(path) -> dict:
    """Return {signal: {count, mean, min, max, std}} for a tidy recording CSV.
    Population standard deviation. Missing file / empty CSV → {}."""
    path = os.fspath(path)
    if not os.path.exists(path):
        return {}
    accs: dict[str, _Acc] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return {}
        for row in reader:
            if len(row) < 3:
                continue
            signal = row[1]
            try:
                value = float(row[2])
            except (ValueError, IndexError):
                continue
            acc = accs.get(signal)
            if acc is None:
                acc = accs[signal] = _Acc()
            acc.add(value)
    return {sig: acc.result() for sig, acc in sorted(accs.items())}
