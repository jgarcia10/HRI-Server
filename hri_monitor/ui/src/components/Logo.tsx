const GRADIENT_ID = "hri-logo-gradient";

/** Hex-cell + pulse mark. `mono` renders in currentColor for monochrome contexts. */
export function Logo({ size = 28, mono = false }: { size?: number; mono?: boolean }) {
  const stroke = mono ? "currentColor" : `url(#${GRADIENT_ID})`;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-label="HRI Monitor logo">
      {!mono && (
        <defs>
          <linearGradient id={GRADIENT_ID} x1="0" y1="0" x2="24" y2="24">
            <stop offset="0" stopColor="#0ea5e9" />
            <stop offset="1" stopColor="#14b8a6" />
          </linearGradient>
        </defs>
      )}
      <path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9L12 3z"
            stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <path d="M7.5 12.5h2.5l2-3 2 5 1.5-2h1"
            stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
