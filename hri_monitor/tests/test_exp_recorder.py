import csv

from hub.bus import MessageBus
from hub.experiments.recorder import Recorder


def read_rows(path):
    with open(path) as f:
        return list(csv.reader(f))


def test_records_tidy_rows_with_offset(tmp_path):
    bus = MessageBus()
    p = tmp_path / "rec.csv"
    r = Recorder(bus, p, start_ts=100.0)
    r.start()
    bus.publish("shimmer.gsr", {"value": 4.2})
    bus.publish("thermal.temps", {"forehead": 34.5, "left_cheek": 33.8,
                                  "right_cheek": 33.9, "nose": 32.5})
    n = r.stop()
    rows = read_rows(p)
    assert rows[0] == ["t_offset", "signal", "value"]
    signals = [row[1] for row in rows[1:]]
    assert "shimmer.gsr" in signals
    assert signals.count("thermal.forehead") == 1
    assert n == len(rows) - 1
    assert all(float(row[0]) >= 0 for row in rows[1:])


def test_unrecorded_topics_ignored(tmp_path):
    bus = MessageBus()
    p = tmp_path / "rec.csv"
    r = Recorder(bus, p, start_ts=0.0)
    r.start()
    bus.publish("device.status", {"device": "rgb", "status": "connected"})
    bus.publish("thermal.frame", {"frame": object()})
    n = r.stop()
    assert n == 0
    assert read_rows(p) == [["t_offset", "signal", "value"]]


def test_stop_is_idempotent(tmp_path):
    bus = MessageBus()
    r = Recorder(bus, tmp_path / "r.csv", start_ts=0.0)
    r.start()
    assert r.stop() == r.stop()


def test_malformed_payload_does_not_break_recorder(tmp_path):
    # A recorded topic with a missing field must NOT crash the recorder — it
    # should skip that sample and keep recording subsequent good ones.
    bus = MessageBus()
    p = tmp_path / "r.csv"
    r = Recorder(bus, p, start_ts=0.0)
    r.start()
    bus.publish("shimmer.gsr", {"oops": 1})       # missing "value" — must be skipped
    bus.publish("shimmer.gsr", {"value": 5.0})    # good — must be recorded
    r.stop()
    signals = [row[1] for row in read_rows(p)[1:]]
    assert signals == ["shimmer.gsr"]             # exactly the one good sample


def test_stop_during_active_flushing_is_safe(tmp_path):
    # Hammer publishes from another thread while stopping, to exercise the
    # timer/stop interleaving. Must not raise and must not lose the header.
    import threading as _t
    bus = MessageBus()
    p = tmp_path / "r.csv"
    r = Recorder(bus, p, start_ts=0.0, flush_interval=0.01)
    r.start()
    stop_flag = {"go": True}

    def spam():
        while stop_flag["go"]:
            bus.publish("shimmer.gsr", {"value": 1.0})

    th = _t.Thread(target=spam, daemon=True)
    th.start()
    import time as _time
    _time.sleep(0.05)
    n = r.stop()           # must not raise
    stop_flag["go"] = False
    th.join(timeout=1)
    rows = read_rows(p)
    assert rows[0] == ["t_offset", "signal", "value"]
    assert n == len(rows) - 1   # count matches written rows exactly
