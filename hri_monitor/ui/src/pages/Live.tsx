import { Eye, HeartPulse, Thermometer, Waves, Wifi, WifiOff } from "lucide-react";
import { SignalChart } from "../components/SignalChart";
import { StatusChip } from "../components/StatusChip";
import { VideoFeed } from "../components/VideoFeed";
import { useLiveData } from "../lib/ws";

export function Live() {
  const { latest, series, devices, connected } = useLiveData();
  const temps = latest["thermal.temps"];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
          style={{
            color: connected ? "var(--ok)" : "var(--warn)",
            background: `color-mix(in srgb, ${connected ? "var(--ok)" : "var(--warn)"} 12%, transparent)`,
          }}
        >
          {connected ? <Wifi size={13} /> : <WifiOff size={13} />} hub
        </span>
        {Object.entries(devices).map(([name, status]) => (
          <StatusChip key={name} name={name} status={status} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <VideoFeed title="Thermal" src="/stream/thermal" />
        <VideoFeed title="RGB" src="/stream/rgb" />
        <div className="glass p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
            <Thermometer size={15} /> Facial temperatures
          </h3>
          {temps ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(temps).map(([roi, v]) => (
                <div
                  key={roi}
                  className="flex justify-between rounded-lg px-2 py-1"
                  style={{ background: "color-mix(in srgb, var(--text-muted) 8%, transparent)" }}
                >
                  <dt style={{ color: "var(--text-muted)" }}>{roi.replace("_", " ")}</dt>
                  <dd className="tnum">{(v as number).toFixed(1)}°C</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>Waiting for thermal data…</p>
          )}
          <p className="mt-3 text-xs" style={{ color: "var(--text-muted)", opacity: 0.7 }}>
            Cognitive load & trust estimates arrive in milestone 3.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalChart title="GSR" unit="µS" colorVar="--chart-gsr" icon={Waves}
                     points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="PPG" unit="mV" colorVar="--chart-ppg" icon={HeartPulse} glow={false}
                     points={series["shimmer.ppg"] ?? []} value={latest["shimmer.ppg"]?.value} />
        <SignalChart title="Blink rate" unit="blinks/min" colorVar="--chart-blink" icon={Eye}
                     points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead temp" unit="°C" colorVar="--chart-temp" icon={Thermometer}
                     points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>
    </div>
  );
}
