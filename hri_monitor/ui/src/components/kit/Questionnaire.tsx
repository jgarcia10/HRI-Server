/**
 * Post-block questionnaires on the participant screen (NASA-TLX, then the trust scale).
 *
 * Unlike the rest of the screen — which is read at ~1.5 m and never touched — this view is
 * *operated* by the participant, on a touchscreen or with a mouse. So it keeps the dark TV
 * look and the `--u` sizing of `pages/Screen.tsx` (this renders inside its `.sc` stage and
 * inherits every variable) but every target is at least 56 px tall, one instrument is shown
 * at a time, and nothing is pre-selected: an unanswered item has to *look* unanswered, and
 * Continue stays dead until all of them are answered. The participant never sees a key like
 * `mental_demand` — only the instrument's own `question` / `low` / `high` wording.
 *
 * The two scales are drawn from `instrument.scale`, not from the instrument name: a scale
 * with many steps (NASA-TLX, 0-100 by 5 → 21 ticks) becomes a tick strip with a read-out,
 * a short one (trust, 1-7) becomes a row of big number buttons.
 */
import { useEffect, useRef, useState } from "react";
import {
  submitQuestionnaire,
  type Instrument,
  type QuestionnaireItem,
  type QuestionnaireState,
} from "../../lib/kit";

type Pending = Extract<QuestionnaireState, { status: "pending" }>;

/** Every value the scale allows, in order (0,5,…,100 or 1,…,7). */
function ticksOf(scale: Instrument["scale"]): number[] {
  const step = scale.step > 0 ? scale.step : 1;
  const out: number[] = [];
  for (let v = scale.min; v <= scale.max + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

const CSS = `
.q {
  --touch: max(56px, calc(var(--u) * 3.6));
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  gap: calc(var(--u) * 1);
}
.q-head { flex: none; }
.q-progress {
  display: flex; align-items: baseline; gap: calc(var(--u) * .9);
  flex-wrap: wrap;
}
.q-bars { display: flex; gap: calc(var(--u) * .4); margin-top: calc(var(--u) * .7); }
.q-bar {
  height: calc(var(--u) * .4); flex: 1;
  border-radius: 99px; background: rgba(255,255,255,.14);
}
.q-bar.on { background: var(--accent); }
.q-bar.past { background: rgba(76,194,255,.45); }

/* The six NASA-TLX items do not fit a 16:9 screen at this type size, so the list scrolls.
   A fade alone is not enough — when the fold happens to fall between two cards there is
   nothing visibly cut off — so the count of hidden questions is spelled out on a chip that
   scrolls to them. Neither is painted when everything already fits (the 4 trust items). */
.q-scroll {
  --chip-band: max(52px, calc(var(--u) * 3.3));
  position: relative; flex: 1; min-height: 0; display: flex;
}
.q-scroll.more::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: var(--chip-band);
  height: calc(var(--u) * 2.4);
  background: linear-gradient(rgba(7,12,20,0), rgba(7,12,20,.94));
  pointer-events: none;
}
/* The chip lives in a reserved band under the list, never on top of a question. */
.q-scroll.more { padding-bottom: var(--chip-band); }
.q-more {
  position: absolute; left: 50%; bottom: calc(var(--u) * .25);
  transform: translateX(-50%);
  display: flex; align-items: center; gap: calc(var(--u) * .5);
  height: max(44px, calc(var(--u) * 2.8));
  padding: 0 calc(var(--u) * 1.4);
  border-radius: 99px; border: 1px solid rgba(76,194,255,.45);
  background: rgba(11,25,40,.95); color: var(--accent);
  font-size: calc(var(--u) * 1.2); font-weight: 650;
  cursor: pointer;
}
.q-list {
  flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
  display: flex; flex-direction: column; gap: calc(var(--u) * .75);
  padding: 2px calc(var(--u) * .5) 2px 2px;
}
.q-scroll.more .q-list { padding-bottom: calc(var(--u) * .6); }
.q-item {
  flex: none;
  border: 2px dashed rgba(255,255,255,.16);
  border-radius: calc(var(--u) * 1);
  background: var(--panel);
  padding: calc(var(--u) * .6) calc(var(--u) * 1.2) calc(var(--u) * .5);
}
.q-item.done {
  border-style: solid;
  border-color: rgba(76,194,255,.5);
  background: var(--panel-2);
}
.q-q {
  font-size: calc(var(--u) * 1.62); font-weight: 600; line-height: 1.2;
  display: flex; align-items: baseline; gap: calc(var(--u) * .8);
}
.q-n {
  flex: none; color: var(--muted); font-weight: 700;
  font-size: calc(var(--u) * 1.15); font-variant-numeric: tabular-nums;
}

/* ---- many-step scale: a strip of tappable ticks (NASA-TLX 0-100 by 5) */
.q-ticks {
  display: flex; gap: 2px; align-items: stretch;
  margin-top: calc(var(--u) * .7);
}
.q-tick {
  flex: 1 1 0; min-width: 34px; height: var(--touch);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: calc(var(--u) * .25);
  padding: 0; border: 0; border-radius: calc(var(--u) * .55);
  background: rgba(255,255,255,.05);
  color: var(--muted); cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.q-tick:hover { background: rgba(255,255,255,.12); }
.q-tick-bar {
  width: 3px; height: 32%; border-radius: 99px; background: rgba(255,255,255,.34);
}
.q-tick.major .q-tick-bar { height: 52%; background: rgba(255,255,255,.55); }
.q-tick-num {
  font-size: calc(var(--u) * 1.05); font-weight: 700; font-variant-numeric: tabular-nums;
  opacity: 0;
}
.q-tick.major .q-tick-num { opacity: .8; }
.q-tick.on {
  background: var(--accent); color: #061321;
}
.q-tick.on:hover { background: var(--accent); }
.q-tick.on .q-tick-bar { display: none; }
.q-tick.on .q-tick-num { opacity: 1; font-size: calc(var(--u) * 1.5); }

/* ---- short scale: big number buttons (trust 1-7) */
.q-nums { display: flex; gap: calc(var(--u) * .6); margin-top: calc(var(--u) * .5); }
.q-num {
  flex: 1 1 0; min-width: 56px;
  height: var(--touch);
  border-radius: calc(var(--u) * .8);
  border: 2px solid rgba(255,255,255,.18);
  background: rgba(255,255,255,.05);
  color: var(--fg); cursor: pointer;
  font-size: calc(var(--u) * 2.2); font-weight: 700; font-variant-numeric: tabular-nums;
  -webkit-tap-highlight-color: transparent;
}
.q-num:hover { background: rgba(255,255,255,.12); }
.q-num.on { background: var(--accent); border-color: var(--accent); color: #061321; }

/* ---- anchors under every scale */
.q-anchors {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: calc(var(--u) * 1);
  margin-top: calc(var(--u) * .3);
  font-size: calc(var(--u) * 1.15);
  color: var(--muted);
}
.q-anchors .end { flex: 1; }
.q-anchors .end.hi { text-align: right; }
.q-value {
  flex: none; font-weight: 700;
  border-radius: 99px; padding: calc(var(--u) * .12) calc(var(--u) * .9);
}
.q-value.set { color: var(--accent); background: rgba(76,194,255,.14); }
.q-value.unset { color: var(--muted); border: 1px dashed rgba(255,255,255,.25); }

/* ---- footer */
.q-foot {
  flex: none;
  display: flex; align-items: center; justify-content: space-between;
  gap: calc(var(--u) * 1.5);
  border-top: 1px solid var(--line);
  padding-top: calc(var(--u) * .9);
}
.q-go {
  flex: none;
  min-height: max(64px, calc(var(--u) * 4));
  padding: 0 calc(var(--u) * 3);
  border: 0; border-radius: calc(var(--u) * .9);
  background: var(--accent); color: #061321;
  font-size: calc(var(--u) * 1.8); font-weight: 750;
  cursor: pointer;
}
.q-go:disabled {
  background: rgba(255,255,255,.10); color: var(--muted); cursor: not-allowed;
}
.q-err {
  flex: none;
  border: 1px solid rgba(255,90,77,.5); background: rgba(255,90,77,.13);
  color: #ffb3ac;
  border-radius: calc(var(--u) * .8);
  padding: calc(var(--u) * .7) calc(var(--u) * 1.1);
  font-size: calc(var(--u) * 1.2);
}
@media (prefers-reduced-motion: no-preference) {
  .q-tick, .q-num, .q-go { transition: background-color .12s ease, color .12s ease; }
}
`;

export function Questionnaire({
  state,
  onSubmitted,
}: {
  state: Pending;
  /** The POST answers with the hub's next state — applied straight away so the
      participant is not left staring at the item they just finished. */
  onSubmitted?: (next: QuestionnaireState) => void;
}) {
  const key = state.next;
  const instrument = key ? state.instruments[key] : undefined;
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // How many questions are still hidden below the fold; 0 when the instrument fits, and the
  // fade / chip (and the space they need) are then not painted at all.
  const [below, setBelow] = useState(0);
  const list = useRef<HTMLDivElement>(null);

  const measure = () => {
    const el = list.current;
    if (!el) return;
    const fold = el.scrollTop + el.clientHeight;
    setBelow(
      Array.from(el.children).filter(
        (c) => (c as HTMLElement).offsetTop + (c as HTMLElement).offsetHeight > fold + 4,
      ).length,
    );
  };

  const scrollDown = () => {
    const el = list.current;
    if (!el) return;
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ top: el.clientHeight * 0.85, behavior: smooth ? "smooth" : "auto" });
  };

  // A fresh instrument starts blank and at the top — never carry a value across.
  useEffect(() => {
    setAnswers({});
    setError(null);
    setBusy(false);
    if (list.current) list.current.scrollTop = 0;
  }, [key]);

  useEffect(() => {
    const el = list.current;
    if (!el) return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    for (const child of Array.from(el.children)) ro.observe(child);
    return () => ro.disconnect();
  }, [key]);

  if (!key || !instrument) return null;

  const items = instrument.items ?? [];
  const values = ticksOf(instrument.scale);
  const wide = values.length > 9;
  const answered = items.filter((it) => answers[it.key] !== undefined).length;
  const complete = items.length > 0 && answered === items.length;
  const index = Math.max(0, state.order.indexOf(key));
  const last = index === state.order.length - 1;

  const send = () => {
    if (!complete || busy) return;
    setBusy(true);
    setError(null);
    submitQuestionnaire(key, answers)
      .then((next) => onSubmitted?.(next as QuestionnaireState))
      .catch((e) => {
        setError(String(e?.message ?? e));
        setBusy(false);
      });
  };

  return (
    <div className="q">
      <style>{CSS}</style>

      <div className="q-head">
        <div className="q-progress">
          <span className="label">
            Questionnaire {index + 1} of {state.order.length}
          </span>
          <span className="big">{instrument.title}</span>
          <span className="muted" style={{ marginLeft: "auto", fontSize: "calc(var(--u) * 1.2)" }}>
            {answered} of {items.length} answered
          </span>
        </div>
        <div className="q-bars">
          {state.order.map((k, i) => (
            <div key={k} className={`q-bar ${i === index ? "on" : i < index ? "past" : ""}`} />
          ))}
        </div>
      </div>

      <div className={`q-scroll ${below > 0 ? "more" : ""}`}>
        <div className="q-list" ref={list} onScroll={measure}>
          {items.map((item, i) => (
            <Item
              key={item.key}
              n={i + 1}
              item={item}
              values={values}
              wide={wide}
              value={answers[item.key]}
              onPick={(v) => setAnswers((a) => ({ ...a, [item.key]: v }))}
            />
          ))}
        </div>
        {below > 0 && (
          <button type="button" className="q-more" onClick={scrollDown} title="Show the rest">
            {below} more {below === 1 ? "question" : "questions"} below
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                 strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 9 l6 7 l6 -7" />
            </svg>
          </button>
        )}
      </div>

      {error && <div className="q-err">{error}</div>}

      <div className="q-foot">
        <div className="muted" style={{ fontSize: "calc(var(--u) * 1.25)" }}>
          {complete
            ? last
              ? "That was the last question — thank you."
              : "All answered — one short set left."
            : `Tap an answer for every question — ${items.length - answered} left.`}
        </div>
        <button
          type="button"
          className="q-go"
          disabled={!complete || busy}
          onClick={send}
          title={complete ? "Send your answers" : "Answer every question first"}
        >
          {busy ? "Sending…" : last ? "Finish" : "Continue"}
        </button>
      </div>
    </div>
  );
}

function Item({
  n,
  item,
  values,
  wide,
  value,
  onPick,
}: {
  n: number;
  item: QuestionnaireItem;
  values: number[];
  wide: boolean;
  value: number | undefined;
  onPick: (v: number) => void;
}) {
  const set = value !== undefined;
  return (
    <div className={`q-item ${set ? "done" : ""}`}>
      <div className="q-q">
        <span className="q-n">{n}.</span>
        <span>{item.question}</span>
      </div>

      {wide ? (
        <div className="q-ticks" role="radiogroup" aria-label={item.question}>
          {values.map((v, i) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={value === v}
              aria-label={String(v)}
              className={`q-tick ${value === v ? "on" : ""} ${i % 5 === 0 ? "major" : ""}`}
              onClick={() => onPick(v)}
            >
              <span className="q-tick-bar" />
              <span className="q-tick-num">{v}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="q-nums" role="radiogroup" aria-label={item.question}>
          {values.map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={value === v}
              className={`q-num ${value === v ? "on" : ""}`}
              onClick={() => onPick(v)}
            >
              {v}
            </button>
          ))}
        </div>
      )}

      <div className="q-anchors">
        <span className="end">{item.low}</span>
        <span className={`q-value ${set ? "set" : "unset"}`}>
          {set ? value : "Not answered yet"}
        </span>
        <span className="end hi">{item.high}</span>
      </div>
    </div>
  );
}

/** Shown for a few seconds after the last instrument, before the welcome screen returns. */
export function QuestionnaireThanks() {
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
      <svg
        viewBox="0 0 48 48"
        style={{ width: "calc(var(--u) * 7)", height: "calc(var(--u) * 7)" }}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="24" cy="24" r="20" strokeWidth="2.5" opacity=".5" />
        <path d="M14 25 l7 7 l14 -16" />
      </svg>
      <div className="huge" style={{ marginTop: "calc(var(--u) * 1.4)" }}>
        Thank you — you&rsquo;re done with this round
      </div>
      <p className="muted" style={{ fontSize: "calc(var(--u) * 1.7)", marginTop: "calc(var(--u) * .9)" }}>
        Take a short break. The screen will tell you when the next round starts.
      </p>
    </div>
  );
}

export default Questionnaire;
