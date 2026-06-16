import { useState } from "react";
import { ManageTab } from "../components/exp/ManageTab";
import { RunTab } from "../components/exp/RunTab";
import { BrowseTab } from "../components/exp/BrowseTab";
import { useActiveRecording, useExperiment, useExperiments } from "../lib/experiments";

const TABS = ["Manage", "Run", "Browse"] as const;
type Tab = (typeof TABS)[number];

export function Experiments() {
  const [tab, setTab] = useState<Tab>("Manage");
  const [selected, setSelected] = useState<number | null>(null);
  const { experiments, refresh: refreshList } = useExperiments();
  const { exp, participants, refresh } = useExperiment(selected);
  const active = useActiveRecording();

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className="rounded-lg px-4 py-2 text-sm font-semibold"
            style={tab === t
              ? { background: "color-mix(in srgb, var(--accent) 15%, transparent)", color: "var(--accent)" }
              : { color: "var(--text-muted)" }}>{t}</button>
        ))}
        {active && <span className="ml-auto self-center text-xs" style={{ color: "var(--err)" }}>● recording</span>}
      </div>
      {tab === "Manage" && (
        <ManageTab experiments={experiments} selected={selected} onSelect={setSelected}
          exp={exp} participants={participants} refresh={refresh} refreshList={refreshList} />
      )}
      {tab === "Run" && <RunTab exp={exp} participants={participants} active={active} />}
      {tab === "Browse" && <BrowseTab exp={exp} participants={participants} />}
    </div>
  );
}
