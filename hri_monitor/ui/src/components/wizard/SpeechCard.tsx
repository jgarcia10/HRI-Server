/**
 * Transcription of what the participant says. Every line goes to the perception model, so the
 * quick phrases cover the things people say most often and the box takes the rest verbatim.
 */
import { useState } from "react";
import { CornerDownLeft, MessageSquare, Send } from "lucide-react";
import { Btn, Card } from "./ui";

const QUICK = ["wait", "faster", "slower", "give me the red one", "put it on the left"];

export function SpeechCard({
  active,
  error,
  sent,
  onSend,
}: {
  active: boolean;
  error: string | null;
  /** Newest first; only the last few are shown. */
  sent: string[];
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const send = (value: string) => {
    const v = value.trim();
    if (!v) return;
    onSend(v);
    setText("");
  };
  return (
    <Card
      icon={MessageSquare}
      title="What the participant said"
      hint="Type it as they say it — the assistant reads this."
      error={error}
    >
      <div className="flex flex-wrap gap-2">
        {QUICK.map((phrase) => (
          <Btn
            key={phrase}
            size="sm"
            variant="quiet"
            disabled={!active}
            title={active ? `Log: “${phrase}”` : "Start a block first"}
            onClick={() => onSend(phrase)}
          >
            “{phrase}”
          </Btn>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "color-mix(in srgb, var(--text-muted) 8%, transparent)",
            border: "1px solid color-mix(in srgb, var(--text-muted) 22%, transparent)",
            color: "var(--text)",
          }}
          placeholder={active ? "Type what they said…" : "Start a block first"}
          value={text}
          disabled={!active}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              send(text);
            }
          }}
        />
        <Btn
          variant="primary"
          icon={Send}
          disabled={!active || !text.trim()}
          title={
            !active ? "Start a block first" : !text.trim() ? "Nothing to send yet" : "Send (Enter)"
          }
          onClick={() => send(text)}
        >
          Send
        </Btn>
      </div>

      {sent.length > 0 && (
        <ul className="space-y-1 text-sm">
          {sent.slice(0, 3).map((line, i) => (
            <li
              key={`${line}-${i}`}
              className="flex items-start gap-2 rounded-lg px-2.5 py-1.5"
              style={{
                background: "color-mix(in srgb, var(--text-muted) 7%, transparent)",
                opacity: 1 - i * 0.25,
              }}
            >
              <CornerDownLeft size={14} className="mt-1 shrink-0" style={{ color: "var(--text-muted)" }} />
              <span>“{line}”</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
