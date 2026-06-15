from hub.bluetooth import parse_devices


def test_parse_bluetoothctl_devices():
    text = (
        "Device 00:06:66:8C:4A:2C Shimmer3-4A2C\n"
        "Device A8:51:AB:CD:EF:01 JBL Flip\n"
        "garbage line\n"
    )
    paired = {"00:06:66:8C:4A:2C"}
    devs = parse_devices(text, paired)
    assert {"mac": "00:06:66:8C:4A:2C", "name": "Shimmer3-4A2C", "paired": True} in devs
    assert {"mac": "A8:51:AB:CD:EF:01", "name": "JBL Flip", "paired": False} in devs
    assert len(devs) == 2
