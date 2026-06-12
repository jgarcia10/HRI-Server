import { useState } from "react";
import { Live } from "./pages/Live";

const PAGES = ["Live", "Devices", "Experiments", "Analysis", "Models", "Settings"] as const;
type Page = (typeof PAGES)[number];

export default function App() {
  const [page, setPage] = useState<Page>("Live");
  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <aside className="w-52 shrink-0 border-r border-slate-800 p-4">
        <h1 className="text-lg font-semibold text-sky-400 mb-6">HRI Monitor</h1>
        <nav className="space-y-1">
          {PAGES.map((p) => (
            <button key={p} onClick={() => setPage(p)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
                page === p ? "bg-sky-500/15 text-sky-300" : "text-slate-400 hover:bg-slate-900"
              }`}>
              {p}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        {page === "Live" ? <Live /> : (
          <p className="text-slate-500">"{page}" arrives in a later milestone.</p>
        )}
      </main>
    </div>
  );
}
