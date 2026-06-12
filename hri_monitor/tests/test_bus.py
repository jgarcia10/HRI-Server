from hub.bus import MessageBus


def test_subscriber_receives_published_message():
    bus = MessageBus()
    got = []
    bus.subscribe("a.b", got.append)
    bus.publish("a.b", {"value": 1})
    assert len(got) == 1
    assert got[0]["topic"] == "a.b"
    assert got[0]["data"] == {"value": 1}
    assert isinstance(got[0]["ts"], float)


def test_wildcard_subscriber_receives_every_topic():
    bus = MessageBus()
    got = []
    bus.subscribe("*", got.append)
    bus.publish("x", {})
    bus.publish("y", {})
    assert [m["topic"] for m in got] == ["x", "y"]


def test_unsubscribe_stops_delivery():
    bus = MessageBus()
    got = []
    bus.subscribe("a", got.append)
    bus.unsubscribe("a", got.append)
    bus.publish("a", {})
    assert got == []


def test_crashing_subscriber_does_not_block_others():
    bus = MessageBus()
    got = []
    bus.subscribe("t", lambda m: 1 / 0)
    bus.subscribe("t", got.append)
    bus.publish("t", {"ok": True})
    assert len(got) == 1
