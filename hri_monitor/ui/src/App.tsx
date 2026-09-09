import {
  Activity, BarChart3, Bot, Brain, Cpu, FlaskConical, Monitor, Moon, Settings, Sun,
} from "lucide-react";
import { useState } from "react";
import { Logo } from "./components/Logo";
import { useTheme } from "./lib/theme";
import { Analysis } from "./pages/Analysis";
import { Devices } from "./pages/Devices";
import { Experiments } from "./pages/Experiments";
import { Live } from "./pages/Live";
import { Runner } from "./pages/Runner";

const PAGES = [
  { name: "Live", icon: Activity },
  { name: "Devices", icon: Cpu },
  { name: "Experiments", icon: FlaskConical },
  { name: "Analysis", icon: BarChart3 },
  { name: "Kit Study", icon: Bot },
  { name: "Models", icon: Brain },
  { name: "Settings", icon: Settings },
] as const;
type Page = (typeof PAGES)[number]["name"];

// `?page=Kit%20Study` opens a page directly (lab bookmarks, headless screenshots).
function initialPage(): Page {
  const wanted = new URLSearchParams(window.location.search).get("page");
  const hit = PAGES.find((p) => p.name === wanted);
  return hit ? hit.name : "Live";
}

export default function App() {
  const [page, setPage] = useState<Page>(initialPage);
  const { pref, resolved, cycle } = useTheme();
  const ThemeIcon = pref === "system" ? Monitor : resolved === "dark" ? Moon : Sun;

  return (
    <div className="dot-grid flex min-h-screen">
      <aside className="glass sticky top-3 m-3 flex h-[calc(100vh-1.5rem)] w-56 shrink-0 flex-col p-4">
        <div className="mb-6 flex items-center gap-2.5">
          <Logo size={30} />
          <div>
            <h1 className="text-base font-semibold leading-tight">HRI Monitor</h1>
            <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              clinical frost
            </p>
          </div>
        </div>
        <nav className="space-y-1">
          {PAGES.map(({ name, icon: Icon }) => (
            <button
              key={name}
              onClick={() => setPage(name)}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition-colors"
              style={
                page === name
                  ? { color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)" }
                  : { color: "var(--text-muted)" }
              }
            >
              <Icon size={16} /> {name}
            </button>
          ))}
        </nav>
        <button
          onClick={cycle}
          title={`Theme: ${pref} (click to change)`}
          className="mt-auto flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          <ThemeIcon size={16} /> Theme: {pref}
        </button>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        {page === "Live" ? (
          <Live />
        ) : page === "Devices" ? (
          <Devices />
        ) : page === "Experiments" ? (
          <Experiments />
        ) : page === "Analysis" ? (
          <Analysis />
        ) : page === "Kit Study" ? (
          <Runner />
        ) : (
          <div className="glass flex h-40 items-center justify-center text-sm" style={{ color: "var(--text-muted)" }}>
            "{page}" arrives in a later milestone — already dressed in Clinical Frost.
          </div>
        )}
      </main>
    </div>
  );
}
