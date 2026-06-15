from hub.bluetooth import bind_commands, free_rfcomm_index, pair_commands, parse_devices


def test_free_rfcomm_index_skips_taken():
    n, dev = free_rfcomm_index(existing={"/dev/rfcomm0", "/dev/rfcomm1"})
    assert n == 2 and dev == "/dev/rfcomm2"


def test_bind_commands_direct_then_sudo():
    cmds = bind_commands(3, "44:B7:D0:2E:23:FC", 6)
    assert cmds[0] == ["rfcomm", "bind", "3", "44:B7:D0:2E:23:FC", "6"]
    assert cmds[1] == ["sudo", "-n", "rfcomm", "bind", "3", "44:B7:D0:2E:23:FC", "6"]


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
