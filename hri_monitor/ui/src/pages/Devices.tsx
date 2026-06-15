import { Cpu, Link2, Loader2, Thermometer, Waves } from "lucide-react";
import { useState } from "react";
import { DeviceCard, Field, Select } from "../components/DeviceCard";
import { BluetoothScan } from "../components/BluetoothScan";
import { btBind, useDevices } from "../lib/devices";

const FALLBACK_XMLS = ["15030138.xml", "16070070.xml", "first_camera.xml"];

export function Devices() {
  const { state, busy, setConfig, action } = useDevices();
  const d = state.devices;
  const rgb = d.rgb?.config ?? {};
  const thermal = d.thermal?.config ?? {};
  const shimmer = d.shimmer?.config ?? {};
  const xmls = state.options.thermal_xml.length ? state.options.thermal_xml : FALLBACK_XMLS;

  const [binding, setBinding] = useState(false);
  const [bindMsg, setBindMsg] = useState("");

  const bindAndConnect = async () => {
    if (!shimmer.mac) {
      setBindMsg("Scan & pair the Shimmer first so we have its MAC.");
      return;
    }
    setBinding(true);
    setBindMsg("");
    try {
      const r = await btBind(shimmer.mac, shimmer.channel ?? 6);
      setBindMsg(r.ok ? `Bound ${r.port} — connecting…` : (r.reason ?? "bind failed"));
    } finally {
      setBinding(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Thermal */}
      <DeviceCard name="Thermal (Optris)" icon={Thermometer}
        status={d.thermal?.status ?? "disabled"} simulate={thermal.simulate ?? true} busy={busy.thermal}
        onToggleSim={(sim) => setConfig("thermal", { simulate: sim })}
        onRestart={() => action("thermal", "restart")} onDisconnect={() => action("thermal", "disconnect")}>
        <Field label="Calibration">
          <Select value={thermal.xml ?? ""} onChange={(e) => setConfig("thermal", { xml: e.target.value })}>
            <option value="">— select XML —</option>
            {xmls.map((x) => <option key={x} value={x}>{x}</option>)}
          </Select>
        </Field>
        <Field label="Detector"><span className="text-xs" style={{ color: "var(--text-muted)" }}>dlib (thermal-trained)</span></Field>
      </DeviceCard>

      {/* RGB */}
      <DeviceCard name="RGB camera" icon={Cpu}
        status={d.rgb?.status ?? "disabled"} simulate={rgb.simulate ?? true} busy={busy.rgb}
        onToggleSim={(sim) => setConfig("rgb", { simulate: sim })}
        onRestart={() => action("rgb", "restart")} onDisconnect={() => action("rgb", "disconnect")}>
        <Field label="Device">
          <Select value={rgb.index ?? 0} onChange={(e) => setConfig("rgb", { index: Number(e.target.value) })}>
            {state.options.cameras.length === 0 && <option value={rgb.index ?? 0}>/dev/video{rgb.index ?? 0}</option>}
            {state.options.cameras.map((c) => (
              <option key={c.index} value={c.index}>{c.path} — {c.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Resolution">
          <Select value={`${rgb.width ?? 640}x${rgb.height ?? 480}`}
            onChange={(e) => { const [w, h] = e.target.value.split("x").map(Number); setConfig("rgb", { width: w, height: h }); }}>
            <option value="640x480">640×480</option>
            <option value="1280x720">1280×720</option>
          </Select>
        </Field>
      </DeviceCard>

      {/* Shimmer */}
      <DeviceCard name="Shimmer GSR" icon={Waves}
        status={d.shimmer?.status ?? "disabled"} simulate={shimmer.simulate ?? true} busy={busy.shimmer}
        onToggleSim={(sim) => setConfig("shimmer", { simulate: sim })}
        onRestart={() => action("shimmer", "restart")} onDisconnect={() => action("shimmer", "disconnect")}>
        <Field label="Connection">
          <Select value={shimmer.port ?? ""}
            onChange={(e) => setConfig("shimmer", { port: e.target.value, simulate: false })}>
            <option value="">Bluetooth socket (ch {shimmer.channel ?? 1})</option>
            {state.options.serial_ports.map((p) => (
              <option key={p} value={p}>Serial · {p}</option>
            ))}
          </Select>
        </Field>
        <Field label="Channel">
          <Select value={shimmer.channel ?? 1} onChange={(e) => setConfig("shimmer", { channel: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6, 7, 8].map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
        </Field>
        <Field label="MAC"><span className="text-xs" style={{ color: "var(--text)" }}>{shimmer.mac ?? "— not paired —"}</span></Field>
        <Field label="Sampling">
          <Select value={shimmer.sampling_rate ?? 200} onChange={(e) => setConfig("shimmer", { sampling_rate: Number(e.target.value) })}>
            {(state.options.sampling_rates.length ? state.options.sampling_rates : [128, 200, 256, 512]).map((r) => (
              <option key={r} value={r}>{r} Hz</option>
            ))}
          </Select>
        </Field>
        <BluetoothScan onPaired={(mac) => setConfig("shimmer", { mac, simulate: false })} />
        <button onClick={bindAndConnect} disabled={binding}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold"
          style={{ background: "var(--accent)", color: "#fff" }}>
          {binding ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
          Bind &amp; connect (ch {shimmer.channel ?? 6})
        </button>
        {bindMsg && (
          <pre className="whitespace-pre-wrap text-[10px]"
            style={{ color: bindMsg.startsWith("Bound") ? "var(--ok)" : "var(--text-muted)" }}>{bindMsg}</pre>
        )}
      </DeviceCard>
    </div>
  );
}
