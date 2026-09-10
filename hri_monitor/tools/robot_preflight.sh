#!/usr/bin/env bash
# Lab preflight for the UR5: network, dashboard, RTDE, remote-control mode. Run from hri_monitor/.
#   tools/robot_preflight.sh [robot_ip]
IP="${1:-147.250.35.40}"
SUBNET="${IP%.*}"
ok(){ printf '  \033[32m✔\033[0m %s\n' "$*"; }; bad(){ printf '  \033[31m✘\033[0m %s\n' "$*"; }
echo "UR5 preflight → $IP"
if ip -br addr | grep -E "^(en|eth)" | grep -q "$SUBNET\."; then ok "wired interface is on $SUBNET.x: $(ip -br addr | grep -E '^(en|eth)' | grep -o "$SUBNET\.[0-9]*/[0-9]*")"
else bad "no wired $SUBNET.x address — plug the cable and run:  nmcli con up ur5-lab"; fi
if ping -c1 -W1 "$IP" >/dev/null 2>&1; then ok "ping $IP"; else bad "no ping to $IP (cable? robot powered? same subnet?)"; exit 1; fi
for p in 29999:dashboard 30004:RTDE 30002:secondary; do port=${p%%:*}; name=${p##*:}
  if timeout 2 bash -c "echo > /dev/tcp/$IP/$port" 2>/dev/null; then ok "port $port ($name) open"; else bad "port $port ($name) closed"; fi; done
python3 - "$IP" <<'PY'
import socket, sys, time
ip = sys.argv[1]
def dash(cmd):
    s = socket.create_connection((ip, 29999), timeout=4); s.recv(1024)
    s.sendall((cmd + "\n").encode()); time.sleep(0.4); r = s.recv(1024).decode().strip(); s.close(); return r
try:
    ver = dash("PolyscopeVersion"); print("  ·", ver)
    cmds = ["robotmode", "safetystatus", "programState"]
    if "URSoftware 5" in ver or "URSoftware 6" in ver:
        cmds.append("is in remote control")   # e-Series only; CB3 (3.x) has no remote-control mode
    for c in cmds:
        print(f"  · {c}: {dash(c)}")
except Exception as e:
    print("  ✘ dashboard query failed:", e)
PY
.venv/bin/python - "$IP" <<'PY'
import sys
ip = sys.argv[1]
try:
    import rtde_receive
    r = rtde_receive.RTDEReceiveInterface(ip)
    q = [round(v, 2) for v in r.getActualQ()]
    print(f"  ✔ RTDE receive: q={q}  protective_stop={r.isProtectiveStopped()}  estop={r.isEmergencyStopped()}")
    r.disconnect()
except Exception as e:
    print("  ✘ RTDE receive failed:", e)
try:
    import rtde_control
    c = rtde_control.RTDEControlInterface(ip)
    print("  ✔ RTDE control: connected"); c.disconnect()
except Exception as e:
    print("  ✘ RTDE control failed:", e, "\n    → e-Series: Settings → System → Remote Control → Enable, then top-bar Local → Remote Control\n    → CB3: make sure no program is running on the pendant")
PY
echo "next: teach poses →  .venv/bin/python -m hub.kit_study.robotd.teach_poses --ip $IP --out hub/kit_study/configs/calibration.yaml --slots home transit L C R RD1 RD2 RD3 OR1 OR2 OR3 BL1 BL2 SF1 SF2 SF3 LM1 LM2 LM3"
