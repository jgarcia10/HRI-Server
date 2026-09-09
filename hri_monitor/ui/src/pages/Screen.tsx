import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { WifiOff } from "lucide-react";
import { useKitWs, type KitPart, type KitTaskState, type SupplyState } from "../lib/kit";
import { BrickFigure, PartGlyph } from "../components/kit/BrickFigure";
import { colorWord, shapeWord, textOf } from "../components/kit/bricks";
import { placementHint } from "../components/kit/placement";

/* ------------------------------------------------------------------ styling
   The screen is a TV ~1.5 m away. Every size is a multiple of --u, which
   tracks a 16:9 box (19.2px at 1920x1080, 16px at 1600x900), so the layout is
   identical on any projector/TV and body text never drops below ~28px at 1080p. */
const CSS = `
html, body { background: #070c14; margin: 0; }
.sc {
  --u: min(1vw, 1.7778vh);
  --bg: #070c14;
  --panel: rgba(255,255,255,.045);
  --panel-2: rgba(255,255,255,.075);
  --line: rgba(255,255,255,.10);
  --fg: #edf3fa;
  --muted: #93a7be;
  --accent: #4cc2ff;
  --alert: #ff5a4d;
  position: fixed; inset: 0; overflow: hidden;
  background:
    radial-gradient(120% 90% at 50% -20%, rgba(76,194,255,.10), transparent 60%),
    var(--bg);
  color: var(--fg);
  font-size: calc(var(--u) * 1.5);
  line-height: 1.28;
  display: flex; flex-direction: column;
  padding: calc(var(--u) * 1.6);
  gap: calc(var(--u) * 1.2);
}
.sc *, .sc *::before, .sc *::after { box-sizing: border-box; }
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: calc(var(--u) * 1.1);
  padding: calc(var(--u) * 1.3) calc(var(--u) * 1.5);
}
.label {
  font-size: calc(var(--u) * 1.05);
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.big { font-size: calc(var(--u) * 2.55); font-weight: 650; letter-spacing: -.01em; }
.huge { font-size: calc(var(--u) * 3.6); font-weight: 700; letter-spacing: -.02em; }
.muted { color: var(--muted); }
.badge {
  flex: none;
  width: calc(var(--u) * 2.1); height: calc(var(--u) * 2.1);
  border-radius: 999px;
  border: 2px solid rgba(76,194,255,.55);
  color: var(--accent);
  font-size: calc(var(--u) * 1.15); font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
@keyframes scPulse { 0%,100% { opacity: 1 } 50% { opacity: .45 } }
@keyframes scBanner { from { transform: translateY(-40%); opacity: 0 } to { transform: none; opacity: 1 } }
.pulse { animation: scPulse 1.5s ease-in-out infinite; }
.banner { animation: scBanner .35s ease-out; }
@media (prefers-reduced-motion: reduce) {
  .pulse { animation: none; }
  .banner { animation: none; }
}
`;

const SLOT_WORD: Record<string, string> = { L: "LEFT", C: "CENTER", R: "RIGHT" };

/* ------------------------------------------------------------------- shell */

function Stage({ children }: { children: ReactNode }) {
  return (
    <div className="sc">
      <style>{CSS}</style>
      {children}
    </div>
  );
}

function Link({ connected }: { connected: boolean }) {
  if (connected) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: "calc(var(--u) * 1.6)",
        bottom: "calc(var(--u) * 1.2)",
        display: "flex",
        alignItems: "center",
        gap: "calc(var(--u) * .6)",
        color: "var(--muted)",
        fontSize: "calc(var(--u) * 1.05)",
      }}
    >
      <WifiOff size={18} /> Reconnecting…
    </div>
  );
}

/* -------------------------------------------------------------- pictograms */

const STROKE = "#b9cbe0";

function PictoRobot() {
  return (
    <Picto>
      <path d="M20 68 h26" />
      <path d="M33 68 V34" />
      <path d="M33 34 L58 22" />
      <path d="M58 22 v12" />
      <path d="M52 34 h12" />
      <path d="M53 34 v9 M63 34 v9" />
      <rect x="50" y="46" width="18" height="11" rx="2" fill="#d64541" stroke="none" />
      <path d="M72 40 q18 -6 26 14" strokeDasharray="5 6" />
      <path d="M98 48 l0 8 l-7 -5 z" fill={STROKE} stroke="none" />
      <rect x="76" y="60" width="40" height="14" rx="4" />
      <circle cx="86" cy="67" r="2.6" />
      <circle cx="96" cy="67" r="2.6" />
      <circle cx="106" cy="67" r="2.6" />
    </Picto>
  );
}

function PictoTake() {
  return (
    <Picto>
      <rect x="14" y="54" width="92" height="18" rx="5" />
      <circle cx="34" cy="63" r="3" />
      <circle cx="86" cy="63" r="3" />
      <rect x="48" y="34" width="24" height="15" rx="3" fill="#2e86de" stroke="none" />
      <rect x="52" y="28" width="6" height="6" rx="2" fill="#2e86de" stroke="none" />
      <rect x="62" y="28" width="6" height="6" rx="2" fill="#2e86de" stroke="none" />
      <rect x="43" y="24" width="34" height="30" rx="6" stroke="#fff" strokeWidth="3" />
      <path d="M60 20 V6" stroke="#fff" />
      <path d="M53 12 l7 -8 l7 8" stroke="#fff" />
    </Picto>
  );
}

function PictoPlace() {
  return (
    <Picto>
      <rect x="10" y="12" width="44" height="46" rx="5" />
      <rect x="22" y="38" width="20" height="10" rx="2" fill="#d64541" stroke="none" />
      <rect x="22" y="27" width="20" height="10" rx="2" fill="#a3cb38" stroke="none" />
      <path d="M62 40 h22" strokeDasharray="5 5" />
      <path d="M86 40 l-8 -5 v10 z" fill={STROKE} stroke="none" />
      <path d="M92 72 h26" />
      <rect x="94" y="58" width="22" height="12" rx="2" fill="#d64541" stroke="none" />
      <rect x="94" y="45" width="22" height="12" rx="2" fill="#a3cb38" stroke="none" />
      <path d="M105 34 V22" stroke="#fff" />
      <path d="M98 30 l7 8 l7 -8" stroke="#fff" />
    </Picto>
  );
}

function PictoBox() {
  return (
    <Picto>
      <path d="M26 42 h68 v30 h-68 z" />
      <path d="M26 42 l-10 -12 h40 l4 12" />
      <path d="M94 42 l10 -12 h-40 l-4 12" />
      <rect x="52" y="8" width="18" height="10" rx="2" fill="#e67e22" stroke="none" />
      <rect x="52" y="19" width="18" height="10" rx="2" fill="#2e86de" stroke="none" />
    </Picto>
  );
}

function Picto({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 128 80"
      style={{ width: "calc(var(--u) * 8)", height: "calc(var(--u) * 5)", flex: "none" }}
      fill="none"
      stroke={STROKE}
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** The mat in front of the participant, with the live spot lit up. */
function MatPicto({ active }: { active: string | null }) {
  const spots: { key: string; cx: number }[] = [
    { key: "L", cx: 46 },
    { key: "C", cx: 110 },
    { key: "R", cx: 174 },
  ];
  return (
    <svg
      viewBox="0 0 220 92"
      style={{ width: "100%", height: "auto" }}
      aria-hidden="true"
    >
      <rect x="4" y="6" width="212" height="60" rx="10" fill="rgba(255,255,255,.07)" stroke="rgba(255,255,255,.18)" strokeWidth="2" />
      {spots.map((s) => {
        const on = s.key === active;
        return (
          <g key={s.key}>
            {on && <circle cx={s.cx} cy={36} r={26} fill="rgba(76,194,255,.18)" className="pulse" />}
            <circle
              cx={s.cx}
              cy={36}
              r={18}
              fill={on ? "var(--accent)" : "transparent"}
              stroke={on ? "var(--accent)" : "rgba(255,255,255,.28)"}
              strokeWidth="2.5"
              strokeDasharray={on ? undefined : "6 6"}
            />
            <text
              x={s.cx}
              y={86}
              textAnchor="middle"
              fontSize="15"
              fontWeight={on ? 700 : 500}
              fill={on ? "var(--accent)" : "rgba(255,255,255,.4)"}
            >
              {SLOT_WORD[s.key]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* --------------------------------------------------------------- countdown */

function useCountdown(remaining: number | null) {
  const [value, setValue] = useState<number | null>(remaining);
  const anchor = useRef<{ t: number; v: number } | null>(null);
  const live = remaining !== null;

  useEffect(() => {
    if (remaining === null) {
      anchor.current = null;
      setValue(null);
      return;
    }
    anchor.current = { t: Date.now(), v: remaining };
    setValue(remaining);
  }, [remaining]);

  useEffect(() => {
    if (!live) return;
    // The hub ticks about once a second; interpolate between ticks so the ring
    // and the digits do not stutter on a big screen.
    const id = setInterval(() => {
      const a = anchor.current;
      if (a) setValue(Math.max(0, a.v - (Date.now() - a.t) / 1000));
    }, 120);
    return () => clearInterval(id);
  }, [live]);

  return value;
}

function Timer({ remaining, total }: { remaining: number; total: number }) {
  const low = remaining <= 30;
  const frac = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0;
  const R = 44;
  const C = 2 * Math.PI * R;
  const mm = Math.floor(Math.ceil(remaining) / 60);
  const ss = Math.ceil(remaining) % 60;
  const color = low ? "var(--alert)" : "var(--accent)";
  return (
    <div
      className={low ? "pulse" : undefined}
      style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * .9)" }}
    >
      <svg viewBox="0 0 100 100" style={{ width: "calc(var(--u) * 5.4)", height: "calc(var(--u) * 5.4)" }}>
        <circle cx="50" cy="50" r={R} fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={R}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - frac)}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div>
        <div className="label" style={{ color: low ? "var(--alert)" : "var(--muted)" }}>
          Time left
        </div>
        <div
          style={{
            fontSize: "calc(var(--u) * 3.4)",
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
            color: low ? "var(--alert)" : "var(--fg)",
            lineHeight: 1.05,
          }}
        >
          {mm}:{String(ss).padStart(2, "0")}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- pages */

export function Screen() {
  const { task, supply, connected } = useKitWs();

  if (!task || task.phase === "idle") {
    return (
      <Stage>
        <Idle connected={connected} />
        <Link connected={connected} />
      </Stage>
    );
  }
  if (task.phase === "done") {
    return (
      <Stage>
        <Centered>
          <div className="huge">All done — thank you!</div>
          <p className="muted" style={{ fontSize: "calc(var(--u) * 1.7)", marginTop: "calc(var(--u) * 1)" }}>
            You can leave the bricks on the table.
          </p>
        </Centered>
        <Link connected={connected} />
      </Stage>
    );
  }
  if (task.phase === "between_orders") {
    return (
      <Stage>
        <Between task={task} />
        <Link connected={connected} />
      </Stage>
    );
  }
  return (
    <Stage>
      <Running task={task} supply={supply} />
      <Link connected={connected} />
    </Stage>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
      }}
    >
      {children}
    </div>
  );
}

/* --------------------------------------------------------------------- idle */

const DEMO_TOWER: KitPart[] = [
  { id: "d1", type: "1x2", color: "blue", depot_slot: "", pos: [0, 0], high: null, width: 2 },
  { id: "d2", type: "1x2", color: "red", depot_slot: "", pos: [0, 1], high: null, width: 2 },
  { id: "d3", type: "1x1", color: "lime", depot_slot: "", pos: [0, 2], high: null, width: 1 },
  { id: "d4", type: "slope", color: "orange", depot_slot: "", pos: [1, 2], high: "left", width: 1 },
];

const STEPS: { picto: ReactNode; title: string; body: string }[] = [
  {
    picto: <PictoRobot />,
    title: "The robot brings one piece",
    body: "It puts a single brick on the mat in front of you.",
  },
  {
    picto: <PictoTake />,
    title: "Take that piece",
    body: "The screen shows which brick it is and where it is on the mat.",
  },
  {
    picto: <PictoPlace />,
    title: "Put it where the picture shows",
    body: "The white outline marks the spot for the piece in your hand.",
  },
  {
    picto: <PictoBox />,
    title: "Finished figure goes in the box",
    body: "Then wait — the robot starts bringing the next figure.",
  },
];

function Idle({ connected }: { connected: boolean }) {
  return (
    <>
      <div
        style={{
          position: "relative",
          height: "calc(var(--u) * 22)",
          borderRadius: "calc(var(--u) * 1.1)",
          overflow: "hidden",
          border: "1px solid var(--line)",
          flex: "none",
        }}
      >
        <img
          src="/kit/scene.jpg"
          alt=""
          style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 58%" }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(90deg, rgba(7,12,20,.94) 0%, rgba(7,12,20,.82) 38%, rgba(7,12,20,.15) 78%)",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: "calc(var(--u) * 2.2)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            maxWidth: "62%",
          }}
        >
          <div className="huge">Welcome</div>
          <p style={{ fontSize: "calc(var(--u) * 1.75)", marginTop: "calc(var(--u) * .8)" }}>
            You and the robot will build small brick figures together.
            <br />
            This screen always tells you what to do next.
          </p>
          <div
            className="muted"
            style={{ marginTop: "calc(var(--u) * 1.1)", fontSize: "calc(var(--u) * 1.2)" }}
          >
            {connected ? "Waiting for the experimenter to start…" : "Connecting…"}
          </div>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "grid",
          gridTemplateColumns: "1.15fr 1fr",
          gap: "calc(var(--u) * 1.2)",
        }}
      >
        <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="label">How it works</div>
          <div
            style={{
              flex: 1,
              display: "grid",
              gridTemplateRows: "repeat(4, 1fr)",
              gap: "calc(var(--u) * .5)",
              marginTop: "calc(var(--u) * .8)",
            }}
          >
            {STEPS.map((s, i) => (
              <div
                key={s.title}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "calc(var(--u) * 1.1)",
                  borderTop: i === 0 ? "none" : "1px solid var(--line)",
                  paddingTop: i === 0 ? 0 : "calc(var(--u) * .5)",
                }}
              >
                <div className="badge">{i + 1}</div>
                {s.picto}
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "calc(var(--u) * 1.55)", fontWeight: 650 }}>{s.title}</div>
                  <div className="muted" style={{ fontSize: "calc(var(--u) * 1.15)" }}>
                    {s.body}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "calc(var(--u) * 1.2)", minHeight: 0 }}>
          <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div className="label">The picture is the plan</div>
            <div
              style={{
                flex: 1,
                minHeight: 0,
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: "calc(var(--u) * .9)",
                marginTop: "calc(var(--u) * .8)",
              }}
            >
              <Tile caption="what the screen shows">
                <BrickFigure parts={DEMO_TOWER} step={DEMO_TOWER.length} width={2} showGhost={false} />
              </Tile>
              <Tile caption="you build it, piece by piece">
                <img src="/kit/hands.jpg" alt="" style={imgTile} />
              </Tile>
              <Tile caption="the finished figure">
                <img src="/kit/tower.jpg" alt="" style={imgTile} />
              </Tile>
            </div>
          </div>
          <div
            className="card"
            style={{ flex: "none", background: "var(--panel-2)", display: "flex", gap: "calc(var(--u) * 1)" }}
          >
            <div style={{ width: "calc(var(--u) * .28)", background: "var(--accent)", borderRadius: 99, flex: "none" }} />
            <div style={{ fontSize: "calc(var(--u) * 1.25)" }}>
              Some figures are <b>timed</b> — a countdown appears on this screen.
              <br />
              If the plan changes, the picture will tell you.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

const imgTile: CSSProperties = {
  width: "100%",
  height: "100%",
  objectFit: "cover",
  borderRadius: "calc(var(--u) * .6)",
};

function Tile({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, gap: "calc(var(--u) * .4)" }}>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "rgba(255,255,255,.05)",
          borderRadius: "calc(var(--u) * .6)",
          padding: "calc(var(--u) * .4)",
          overflow: "hidden",
        }}
      >
        {children}
      </div>
      <div
        className="muted"
        style={{ fontSize: "calc(var(--u) * 1)", textAlign: "center" }}
      >
        {caption}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ running */

function Running({ task, supply }: { task: KitTaskState; supply: SupplyState | null }) {
  const parts = task.parts ?? [];
  const current = parts[task.step_index] ?? task.current_part ?? null;
  const remaining = useCountdown(task.remaining_s);
  const [total, setTotal] = useState(0);
  const [alert, setAlert] = useState(false);
  // Starts at false on purpose: if the screen is reloaded right after a swap the
  // participant still gets the warning once.
  const prevPerturb = useRef(false);

  useEffect(() => {
    setTotal(0);
  }, [task.order_id]);
  useEffect(() => {
    if (task.remaining_s !== null) {
      setTotal((t) => (task.remaining_s! > t ? Math.ceil(task.remaining_s! / 10) * 10 : t));
    }
  }, [task.remaining_s]);

  useEffect(() => {
    if (task.perturbation_applied && !prevPerturb.current) {
      setAlert(true);
      const id = setTimeout(() => setAlert(false), 8000);
      prevPerturb.current = true;
      return () => clearTimeout(id);
    }
    prevPerturb.current = task.perturbation_applied;
  }, [task.perturbation_applied]);

  const nFigures = task.order_index + 1 + (task.queue?.length ?? 0);
  const slot = current && supply?.staged
    ? Object.keys(supply.staged).find((k) => supply.staged[k] === current.id) ?? null
    : null;
  const hint = current ? placementHint(parts, task.step_index) : null;

  return (
    <>
      {/* header */}
      <div
        style={{
          flex: "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "calc(var(--u) * 2)",
          padding: "0 calc(var(--u) * .4)",
        }}
      >
        <div>
          <div className="label">
            Figure {task.order_index + 1} of {nFigures}
          </div>
          <div className="big" style={{ marginTop: "calc(var(--u) * .15)" }}>
            {task.order_name ?? "Figure"}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1)" }}>
          <div style={{ textAlign: "right" }}>
            <div className="label">Piece</div>
            <div style={{ fontSize: "calc(var(--u) * 1.7)", fontWeight: 650 }}>
              {task.step_index + 1} of {task.n_parts}
            </div>
          </div>
          <div style={{ display: "flex", gap: "calc(var(--u) * .32)" }}>
            {parts.map((p, i) => (
              <div
                key={p.id + i}
                className={i === task.step_index ? "pulse" : undefined}
                style={{
                  width: "calc(var(--u) * .58)",
                  height: "calc(var(--u) * 1.7)",
                  borderRadius: "calc(var(--u) * .2)",
                  background:
                    i < task.step_index
                      ? "var(--accent)"
                      : i === task.step_index
                        ? "#ffffff"
                        : "rgba(255,255,255,.16)",
                }}
              />
            ))}
          </div>
        </div>

        {remaining !== null && (
          <div style={{ minWidth: "calc(var(--u) * 11)", display: "flex", justifyContent: "flex-end" }}>
            <Timer remaining={remaining} total={total} />
          </div>
        )}
      </div>

      {alert && (
        <div
          className="banner"
          style={{
            flex: "none",
            background: "#ffffff",
            color: "#0a1220",
            borderRadius: "calc(var(--u) * 1.1)",
            padding: "calc(var(--u) * 1) calc(var(--u) * 1.6)",
            display: "flex",
            alignItems: "center",
            gap: "calc(var(--u) * 1.2)",
          }}
        >
          <svg viewBox="0 0 48 48" style={{ width: "calc(var(--u) * 2.6)", height: "calc(var(--u) * 2.6)", flex: "none" }} fill="none" stroke="#0a1220" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 17 h27 l-7 -7 M40 31 h-27 l7 7" />
          </svg>
          <div>
            <div style={{ fontSize: "calc(var(--u) * 2.1)", fontWeight: 750 }}>The plan changed</div>
            <div style={{ fontSize: "calc(var(--u) * 1.3)", opacity: 0.8 }}>
              Look at the picture again — the order of the pieces is different now.
            </div>
          </div>
        </div>
      )}

      {/* body */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "grid",
          gridTemplateColumns: "1.42fr 1fr",
          gap: "calc(var(--u) * 1.2)",
        }}
      >
        <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="label">Build this</div>
          <div style={{ flex: 1, minHeight: 0, padding: "calc(var(--u) * .8) 0" }}>
            <BrickFigure parts={parts} step={task.step_index} width={task.width_studs} />
          </div>
          <div className="muted" style={{ fontSize: "calc(var(--u) * 1.05)", textAlign: "center" }}>
            White outline = the piece to place now · dotted = still to come
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "calc(var(--u) * 1.2)", minHeight: 0 }}>
          <Step n={1} title="Take this piece" grow>
            {current ? (
              <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1.2)" }}>
                <div
                  style={{
                    flex: "none",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "calc(var(--u) * 7.4)",
                    height: "calc(var(--u) * 5.2)",
                    padding: "calc(var(--u) * .6)",
                    borderRadius: "calc(var(--u) * .7)",
                    background: "rgba(255,255,255,.06)",
                  }}
                >
                  <PartGlyph part={current} />
                </div>
                <div style={{ fontSize: "calc(var(--u) * 2.3)", fontWeight: 700, lineHeight: 1.15 }}>
                  the{" "}
                  <span style={{ color: textOf(current.color), textTransform: "uppercase" }}>
                    {colorWord(current.color)}
                  </span>
                  <br />
                  {shapeWord(current.type)}
                </div>
              </div>
            ) : null}
          </Step>

          <Step n={2} title="Where it is" grow>
            {slot ? (
              <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1.2)" }}>
                <div style={{ width: "calc(var(--u) * 11.5)", flex: "none" }}>
                  <MatPicto active={slot} />
                </div>
                <div style={{ fontSize: "calc(var(--u) * 1.6)" }}>
                  On the mat —{" "}
                  <b style={{ color: "var(--accent)", fontSize: "calc(var(--u) * 2.1)" }}>
                    {SLOT_WORD[slot] ?? slot}
                  </b>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1.2)" }}>
                <PictoRobot />
                <div style={{ fontSize: "calc(var(--u) * 1.6)" }} className="pulse">
                  The robot is bringing it…
                </div>
              </div>
            )}
          </Step>

          <Step n={3} title="Where it goes" grow>
            <div style={{ fontSize: "calc(var(--u) * 1.85)", lineHeight: 1.25 }}>{hint?.text}</div>
            {hint?.note && (
              <div
                style={{
                  marginTop: "calc(var(--u) * .7)",
                  display: "inline-block",
                  border: "2px solid var(--accent)",
                  color: "var(--accent)",
                  borderRadius: "calc(var(--u) * .5)",
                  padding: "calc(var(--u) * .25) calc(var(--u) * .8)",
                  fontSize: "calc(var(--u) * 1.4)",
                  fontWeight: 700,
                }}
              >
                {hint.note}
              </div>
            )}
          </Step>
        </div>
      </div>
    </>
  );
}

function Step({
  n,
  title,
  children,
  grow,
}: {
  n: number;
  title: string;
  children: ReactNode;
  grow?: boolean;
}) {
  return (
    <div
      className="card"
      style={{
        flex: grow ? 1 : "none",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "calc(var(--u) * .7)",
          marginBottom: "calc(var(--u) * .8)",
          flex: "none",
        }}
      >
        <div className="badge">{n}</div>
        <div className="label">{title}</div>
      </div>
      <div style={{ flex: grow ? 1 : "none", display: "flex", flexDirection: "column", justifyContent: "center", minHeight: 0 }}>
        {children}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- between orders */

function Between({ task }: { task: KitTaskState }) {
  const parts = task.parts ?? [];
  const more = (task.queue?.length ?? 0) > 0;
  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: "grid",
        gridTemplateColumns: "1fr 1.25fr",
        gap: "calc(var(--u) * 1.6)",
        alignItems: "center",
      }}
    >
      <div className="card" style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div className="label">You built</div>
        <div style={{ flex: 1, minHeight: 0, padding: "calc(var(--u) * .8) 0" }}>
          <BrickFigure parts={parts} step={parts.length} width={task.width_studs} showGhost={false} />
        </div>
      </div>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1.1)" }}>
          <svg
            viewBox="0 0 48 48"
            style={{ width: "calc(var(--u) * 4)", height: "calc(var(--u) * 4)", flex: "none" }}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="24" cy="24" r="20" strokeWidth="3" opacity=".5" />
            <path d="M14 25 l7 7 l14 -16" />
          </svg>
          <div className="huge">{task.order_name ?? "Figure"} complete</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "calc(var(--u) * 1.4)", marginTop: "calc(var(--u) * 1.6)" }}>
          <PictoBox />
          <div style={{ fontSize: "calc(var(--u) * 2.1)", fontWeight: 650 }}>
            Put the finished figure in the box.
          </div>
        </div>
        <div
          className="muted"
          style={{ fontSize: "calc(var(--u) * 1.5)", marginTop: "calc(var(--u) * 1.6)" }}
        >
          {more ? "Then wait — the next figure is coming up." : "That was the last figure."}
        </div>
      </div>
    </div>
  );
}

export default Screen;
