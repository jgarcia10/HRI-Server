"""bluetoothctl wrapper for scan/pair + serial-port listing. Subprocess calls
are timed out; output parsing is pure and unit-tested."""
import getpass
import glob
import os
import re
import subprocess

_DEV_RE = re.compile(r"^Device ([0-9A-F:]{17}) (.+)$")


def free_rfcomm_index(existing=None) -> tuple[int, str]:
    """Pick the lowest unused /dev/rfcommN index. `existing` overridable for tests."""
    taken = existing if existing is not None else set(glob.glob("/dev/rfcomm*"))
    for n in range(0, 64):
        dev = f"/dev/rfcomm{n}"
        if dev not in taken:
            return n, dev
    raise RuntimeError("no free /dev/rfcommN slot")


def bind_commands(index: int, mac: str, channel: int) -> list[list[str]]:
    """Escalation ladder for `rfcomm bind <index> <mac> <channel>`: try direct
    (in case the user has the capability), then non-interactive sudo."""
    base = ["rfcomm", "bind", str(index), mac, str(channel)]
    return [base, ["sudo", "-n", *base]]


def bind_rfcomm(mac: str, channel: int = 1, index=None) -> dict:
    """Bind a persistent /dev/rfcommN for `mac` on `channel`. Returns
    {ok, port, reason}. On a privilege failure, `reason` carries the one-time
    passwordless-sudo setup + the manual command.

    `rfcomm bind` can exit 0 without actually creating the node when it lacks
    privilege, so success is confirmed by the node appearing — not the exit code.
    """
    try:
        n, dev = (index, f"/dev/rfcomm{index}") if index is not None else free_rfcomm_index()
    except RuntimeError as e:
        return {"ok": False, "reason": str(e)}
    last = ""
    for cmd in bind_commands(n, mac, channel):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and _wait_for_node(dev):
                return {"ok": True, "port": dev}
            last = (r.stderr or r.stdout or "").strip() or "rfcomm reported success but no device appeared (no privilege?)"
        except FileNotFoundError:
            last = "rfcomm not installed"
        except Exception as e:  # noqa: BLE001
            last = str(e)
    user = getpass.getuser()
    hint = (f"rfcomm needs root. Enable one-click binding by running this ONCE:\n"
            f"  echo '{user} ALL=(ALL) NOPASSWD: {_which_rfcomm()}' | sudo tee /etc/sudoers.d/hri-rfcomm\n"
            f"Then click again. Or bind manually:  sudo rfcomm bind {n} {mac} {channel}")
    return {"ok": False, "reason": f"{last}\n{hint}" if last else hint}


def _wait_for_node(dev: str, timeout: float = 2.0) -> bool:
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.path.exists(dev):
            return True
        time.sleep(0.1)
    return os.path.exists(dev)


def release_rfcomm(port: str) -> dict:
    """Release a bound /dev/rfcommN (best-effort)."""
    n = port.rsplit("rfcomm", 1)[-1]
    for cmd in (["rfcomm", "release", n], ["sudo", "-n", "rfcomm", "release", n]):
        try:
            if subprocess.run(cmd, capture_output=True, text=True, timeout=10).returncode == 0:
                return {"ok": True}
        except Exception:  # noqa: BLE001
            continue
    return {"ok": False}


def _which_rfcomm() -> str:
    for p in ("/usr/bin/rfcomm", "/bin/rfcomm"):
        if os.path.exists(p):
            return p
    return "/usr/bin/rfcomm"


def parse_devices(text: str, paired_macs: set) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _DEV_RE.match(line.strip())
        if not m:
            continue
        mac, name = m.group(1), m.group(2).strip()
        out.append({"mac": mac, "name": name, "paired": mac in paired_macs})
    return out


def _run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _paired_macs() -> set:
    try:
        r = _run(["bluetoothctl", "paired-devices"], 5)
        return {m.group(1) for line in r.stdout.splitlines()
                if (m := _DEV_RE.match(line.strip()))}
    except Exception:
        return set()


def scan(seconds: int = 8) -> list[dict]:
    try:
        subprocess.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                       capture_output=True, text=True, timeout=seconds + 5)
        r = _run(["bluetoothctl", "devices"], 5)
        return parse_devices(r.stdout, _paired_macs())
    except Exception:
        return []


def pair_commands(mac: str, pin: str = "1234") -> str:
    """bluetoothctl stdin script: register a PIN agent, pair, supply PIN, trust.
    The PIN line is queued after `pair` so it answers the agent's prompt."""
    return "\n".join([
        "agent KeyboardOnly",
        "default-agent",
        f"pair {mac}",
        pin,
        f"trust {mac}",
        "quit",
    ]) + "\n"


def pair(mac: str, pin: str = "1234") -> dict:
    try:
        p = subprocess.run(
            ["bluetoothctl"], input=pair_commands(mac, pin),
            capture_output=True, text=True, timeout=30)
        out = (p.stdout or "") + (p.stderr or "")
        ok = "Paired: yes" in out or "pairing successful" in out.lower()
        return {"ok": ok, "reason": out.strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "pair timed out (confirm/accept PIN on the device or OS)"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def list_serial_ports() -> list[str]:
    return sorted(glob.glob("/dev/rfcomm*") + glob.glob("/dev/ttyUSB*"))
