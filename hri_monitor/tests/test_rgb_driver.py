from hub.bus import MessageBus
from hub.sensors.rgb import RealRGB


def test_realrgb_is_basesensor_with_config():
    bus = MessageBus()
    s = RealRGB(bus, index=2, width=640, height=480, fps=30)
    assert s.name == "rgb"
    assert s.index == 2 and s.width == 640 and s.fps == 30
    assert s.status == "disabled"


def test_realrgb_connect_raises_clean_when_cv2_missing(monkeypatch):
    bus = MessageBus()
    s = RealRGB(bus, index=999, width=640, height=480, fps=30)
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        s.connect()
        raised = False
    except Exception:
        raised = True
    assert raised
