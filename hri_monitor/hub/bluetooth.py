"""bluetoothctl wrapper for scan/pair + serial-port listing. Subprocess calls
are timed out; output parsing is pure and unit-tested."""
import glob
import re
import subprocess

_DEV_RE = re.compile(r"^Device ([0-9A-F:]{17}) (.+)$")


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
