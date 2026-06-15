import { Cpu, Thermometer, Waves } from "lucide-react";
import { DeviceCard, Field, Select } from "../components/DeviceCard";
import { BluetoothScan } from "../components/BluetoothScan";
import { useDevices } from "../lib/devices";

const THERMAL_XMLS = ["15030138.xml", "16070070.xml", "first_camera.xml"];

export function Devices() {
  const { state, busy, setConfig, action } = useDevices();
  const d = state.devices;
  const rgb = d.rgb?.config ?? {};
  const thermal = d.thermal?.config ?? {};
  const shimmer = d.shimmer?.config ?? {};

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Thermal */}
      <DeviceCard name="Thermal (Optris)" icon={Thermometer}
        status={d.thermal?.status ?? "disabled"} simulate={thermal.simulate ?? true} busy={busy.thermal}
        onToggleSim={(sim) => setConfig("thermal", { simulate: sim })}
        onRestart={() => action("thermal", "restart")} onDisconnect={() => action("thermal", "disconnect")}>
        <Field label="Calibration">
          <Select value={thermal.xml ?? ""} onChange={(e) => setConfig("thermal", { xml: e.target.value })}>
            {THERMAL_XMLS.map((x) => <option key={x} value={x}>{x}</option>)}
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
          <Select value={`${rgb.width}x${rgb.height}`}
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
        {!shimmer.port && (
          <Field label="BT channel">
            <Select value={shimmer.channel ?? 1} onChange={(e) => setConfig("shimmer", { channel: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5, 6, 7, 8].map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </Field>
        )}
        <Field label="MAC"><span className="text-xs" style={{ color: "var(--text)" }}>{shimmer.mac ?? "— not paired —"}</span></Field>
        <Field label="Sampling">
          <Select value={shimmer.sampling_rate ?? 200} onChange={(e) => setConfig("shimmer", { sampling_rate: Number(e.target.value) })}>
            {(state.options.sampling_rates.length ? state.options.sampling_rates : [128, 200, 256, 512]).map((r) => (
              <option key={r} value={r}>{r} Hz</option>
            ))}
          </Select>
        </Field>
        <BluetoothScan onPaired={(mac) => setConfig("shimmer", { mac, simulate: false })} />
        <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
          No serial port? Bind one first: <code>sudo rfcomm connect /dev/rfcomm0 {shimmer.mac ?? "&lt;MAC&gt;"} 6</code> — then pick it above.
        </p>
      </DeviceCard>
    </div>
  );
}
