import { Video, VideoOff } from "lucide-react";
import { useState } from "react";

export function VideoFeed({ title, src }: { title: string; src: string }) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  return (
    <div className="glass p-4">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
        <Video size={15} /> {title}
      </h3>
      {failed ? (
        <button
          onClick={() => {
            setFailed(false);
            setRetry((r) => r + 1);
          }}
          className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl text-sm"
          style={{
            color: "var(--text-muted)",
            background: "color-mix(in srgb, var(--text-muted) 8%, transparent)",
          }}
        >
          <VideoOff size={22} />
          No signal — click to retry
        </button>
      ) : (
        <img
          src={`${src}?r=${retry}`}
          alt={title}
          onError={() => setFailed(true)}
          className="aspect-video w-full rounded-xl bg-black/80 object-contain"
        />
      )}
    </div>
  );
}
