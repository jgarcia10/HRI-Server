import { Bluetooth, Loader2 } from "lucide-react";
import { useState } from "react";
import { btPair, btScan, type BtDevice } from "../lib/devices";

export function BluetoothScan({ onPaired }: { onPaired: (mac: string) => void }) {
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<BtDevice[]>([]);
  const [pairing, setPairing] = useState<string | null>(null);
  const [msg, setMsg] = useState<string>("");

  const scan = async () => {
    setScanning(true);
    setMsg("");
    try {
      setDevices(await btScan(8));
    } finally {
      setScanning(false);
    }
  };

  const pair = async (mac: string) => {
    setPairing(mac);
    setMsg("");
    try {
      const r = await btPair(mac);
      if (r.ok) onPaired(mac);
      else setMsg(r.reason || "pairing failed");
    } finally {
      setPairing(null);
    }
  };

  return (
    <div className="rounded-xl border border-dashed p-2"
      style={{ borderColor: "var(--accent)", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--accent)" }}>
        <Bluetooth size={13} /> Bluetooth
        <button onClick={scan} disabled={scanning}
          className="ml-auto rounded-md px-2 py-1 font-semibold"
          style={{ background: "var(--accent)", color: "#fff" }}>
          {scanning ? "Scanning…" : "Scan"}
        </button>
      </div>
      {devices.map((d) => (
        <div key={d.mac} className="mt-1 flex items-center gap-2 rounded-md px-1 py-1 text-xs"
          style={{ color: "var(--text)" }}>
          <span>{d.paired ? "🔵" : "⚪"}</span>
          <span>{d.name}</span>
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{d.mac}</span>
          <button onClick={() => pair(d.mac)} disabled={pairing === d.mac}
            className="ml-auto rounded-md px-2 py-0.5 font-semibold"
            style={{ color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}>
            {pairing === d.mac ? <Loader2 size={12} className="animate-spin" /> : d.paired ? "Use" : "Pair"}
          </button>
        </div>
      ))}
      {devices.length > 0 && (
        <div className="mt-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
          If prompted, the Shimmer PIN is <b>1234</b>.
        </div>
      )}
      {msg && <div className="mt-1 text-[10px]" style={{ color: "var(--err)" }}>{msg}</div>}
    </div>
  );
}
