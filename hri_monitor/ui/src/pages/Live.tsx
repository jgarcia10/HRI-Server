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
        <StatusChip name="hub" status={connected ? "connected" : "reconnecting"} />
        {Object.entries(devices).map(([name, status]) => (
          <StatusChip key={name} name={name} status={status} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <VideoFeed title="Thermal" src="/stream/thermal" />
        <VideoFeed title="RGB" src="/stream/rgb" />
        <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-2">Facial temperatures</h3>
          {temps ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(temps).map(([roi, v]) => (
                <div key={roi} className="flex justify-between rounded bg-slate-800/60 px-2 py-1">
                  <dt className="text-slate-400">{roi.replace("_", " ")}</dt>
                  <dd className="text-slate-100">{(v as number).toFixed(1)}°C</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-slate-500 text-sm">Waiting for thermal data…</p>
          )}
          <p className="mt-3 text-xs text-slate-600">
            Cognitive load & trust estimates arrive in milestone 3.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <SignalChart title="GSR" unit="µS" color="#38bdf8"
                     points={series["shimmer.gsr"] ?? []} value={latest["shimmer.gsr"]?.value} />
        <SignalChart title="PPG" unit="mV" color="#fb7185"
                     points={series["shimmer.ppg"] ?? []} value={latest["shimmer.ppg"]?.value} />
        <SignalChart title="Blink rate" unit="blinks/min" color="#a78bfa"
                     points={series["rgb.blink"] ?? []} value={latest["rgb.blink"]?.rate} />
        <SignalChart title="Forehead temp" unit="°C" color="#fbbf24"
                     points={series["thermal.temps"] ?? []} value={temps?.forehead} />
      </div>
    </div>
  );
}
