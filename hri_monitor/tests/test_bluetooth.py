from hub.bluetooth import parse_devices, pair_commands


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


def test_pair_commands_includes_agent_pin_and_trust():
    script = pair_commands("00:06:66:8C:4A:2C", "1234")
    lines = script.splitlines()
    assert "agent KeyboardOnly" in lines or "agent on" in lines
    assert "default-agent" in lines
    assert "pair 00:06:66:8C:4A:2C" in lines
    assert "1234" in lines  # PIN supplied to the agent prompt
    assert "trust 00:06:66:8C:4A:2C" in lines
    # PIN must come AFTER the pair command (the agent prompts post-pair)
    assert lines.index("1234") > lines.index("pair 00:06:66:8C:4A:2C")
