import type { CSSProperties } from "react";
import type { KitPart } from "../../lib/kit";
import {
  figureSize,
  fillOf,
  occupiedCells,
  overlaps,
  partLayer,
  partWidth,
  partX,
} from "./bricks";

const U = 100; // internal units: 1 stud = 1 brick height = 100
const PAD_X = 26;
const PAD_TOP = 180; // room for the drop arrow above the top layer
const PAD_TOP_FLAT = 34; // no arrow: keep the figure tight in its box
const PAD_BOTTOM = 78; // room for the table line
const STUD_H = 17;
const STUD_W = 46;

export type BrickFigureProps = {
  /** Assembly sequence, index = step. */
  parts: KitPart[];
  /** How many pieces are already placed (index of the current piece). */
  step: number;
  /** Figure width in studs (task.width_studs). */
  width: number;
  /** Unit size in px. Omit to fill the parent box. */
  size?: number;
  /** Draw the drop arrow above the current piece. Default true. */
  showGhost?: boolean;
  className?: string;
  style?: CSSProperties;
};

type Shape = { d: string; studs: { x: number; y: number }[] };

/** Outline of one brick in svg units, plus the stud positions that stay visible. */
function shapeOf(p: KitPart, height: number, cells: Set<string>, padTop: number): Shape {
  const w = partWidth(p);
  const x = partX(p);
  const layer = partLayer(p);
  const left = PAD_X + x * U;
  const right = left + w * U;
  const bottom = padTop + (height - layer) * U;
  const top = bottom - U;
  const r = 10;

  if (p.type === "slope") {
    // Right triangle, vertical (tall) edge on `high`, hypotenuse falling away.
    const d =
      p.high === "right"
        ? `M ${left} ${bottom} L ${right} ${bottom} L ${right} ${top} Z`
        : `M ${left} ${bottom} L ${right} ${bottom} L ${left} ${top} Z`;
    return { d, studs: [] };
  }

  const d =
    `M ${left + r} ${top} H ${right - r} A ${r} ${r} 0 0 1 ${right} ${top + r}` +
    ` V ${bottom - r} A ${r} ${r} 0 0 1 ${right - r} ${bottom}` +
    ` H ${left + r} A ${r} ${r} 0 0 1 ${left} ${bottom - r}` +
    ` V ${top + r} A ${r} ${r} 0 0 1 ${left + r} ${top} Z`;

  const studs: { x: number; y: number }[] = [];
  for (let i = 0; i < w; i++) {
    if (cells.has(`${x + i},${layer + 1}`)) continue; // hidden behind the brick above
    studs.push({ x: left + i * U + (U - STUD_W) / 2, y: top - STUD_H });
  }
  return { d, studs };
}

/**
 * Front view of a kit figure: bricks on a table line, studs on top, slopes as
 * right triangles. Placed pieces are solid, the current piece is highlighted
 * with a white halo and a drop arrow, still-missing pieces are dashed outlines
 * so the target shape stays readable from the first piece on.
 */
export function BrickFigure({
  parts,
  step,
  width,
  size,
  showGhost = true,
  className,
  style,
}: BrickFigureProps) {
  const { studs: wStuds, layers } = figureSize(parts, width);
  const cells = occupiedCells(parts);
  const current = parts[step];
  const arrow = showGhost && !!current;
  const padTop = arrow ? PAD_TOP : PAD_TOP_FLAT;
  const vbW = wStuds * U + PAD_X * 2;
  const vbH = layers * U + padTop + PAD_BOTTOM;
  const groundY = padTop + layers * U;

  const dims: CSSProperties = size
    ? { width: (vbW / U) * size, height: (vbH / U) * size }
    : { width: "100%", height: "100%" };

  const cur = current ? shapeOf(current, layers, cells, padTop) : null;
  // The drop arrow must not sit on top of another brick: start it above the
  // highest brick that shares a column with the piece being placed.
  let arrowLayer = current ? partLayer(current) + 1 : 0;
  if (current) {
    for (const p of parts) {
      if (p === current) continue;
      if (!overlaps(partX(current), partWidth(current), partX(p), partWidth(p))) continue;
      if (partLayer(p) >= arrowLayer) arrowLayer = partLayer(p) + 1;
    }
  }

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      preserveAspectRatio="xMidYMid meet"
      className={className}
      style={{ ...dims, overflow: "visible", ...style }}
      role="img"
      aria-label="Figure to build"
    >
      <style>{`
        @keyframes bfHalo { 0%,100% { opacity:.85 } 50% { opacity:.28 } }
        @keyframes bfDrop { 0%,100% { transform: translateY(0) } 50% { transform: translateY(26px) } }
        .bf-halo { animation: bfHalo 1.7s ease-in-out infinite; }
        .bf-arrow { animation: bfDrop 1.7s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .bf-halo, .bf-arrow { animation: none; opacity: .8; }
        }
      `}</style>

      {/* table */}
      <line
        x1={0}
        y1={groundY}
        x2={vbW}
        y2={groundY}
        stroke="rgba(230,242,255,.42)"
        strokeWidth={5}
        strokeLinecap="round"
      />

      {/* still missing: dashed target outlines */}
      {parts.map((p, i) => {
        if (i <= step) return null;
        const s = shapeOf(p, layers, cells, padTop);
        return (
          <g key={`f-${p.id}-${i}`}>
            <path d={s.d} fill={fillOf(p.color)} fillOpacity={0.17} />
            <path
              d={s.d}
              fill="none"
              stroke="rgba(226,240,255,.45)"
              strokeWidth={4.5}
              strokeDasharray="16 14"
            />
            {s.studs.map((st, k) => (
              <rect
                key={k}
                x={st.x}
                y={st.y}
                width={STUD_W}
                height={STUD_H + 6}
                rx={6}
                fill="none"
                stroke="rgba(226,240,255,.26)"
                strokeWidth={3}
                strokeDasharray="10 9"
              />
            ))}
          </g>
        );
      })}

      {/* already placed */}
      {parts.map((p, i) => {
        if (i >= step) return null;
        const s = shapeOf(p, layers, cells, padTop);
        return (
          <g key={`p-${p.id}-${i}`}>
            {s.studs.map((st, k) => (
              <rect
                key={k}
                x={st.x}
                y={st.y}
                width={STUD_W}
                height={STUD_H + 8}
                rx={6}
                fill={fillOf(p.color)}
              />
            ))}
            <path d={s.d} fill={fillOf(p.color)} />
            <path d={s.d} fill="none" stroke="rgba(0,0,0,.32)" strokeWidth={3} />
          </g>
        );
      })}

      {/* the piece to place now */}
      {current && cur && (
        <g>
          <path
            className="bf-halo"
            d={cur.d}
            fill="none"
            stroke="#ffffff"
            strokeWidth={30}
            strokeLinejoin="round"
          />
          {cur.studs.map((st, k) => (
            <rect
              key={k}
              x={st.x}
              y={st.y}
              width={STUD_W}
              height={STUD_H + 8}
              rx={6}
              fill={fillOf(current.color)}
            />
          ))}
          <path d={cur.d} fill={fillOf(current.color)} />
          <path
            d={cur.d}
            fill="none"
            stroke="#ffffff"
            strokeWidth={9}
            strokeLinejoin="round"
          />
          {arrow && (
            <g
              transform={`translate(${PAD_X + (partX(current) + partWidth(current) / 2) * U}, ${
                padTop + (layers - arrowLayer) * U
              })`}
            >
              {/* the animation lives on an inner group: a CSS transform would
                  otherwise replace the positioning transform attribute above */}
              <g className="bf-arrow">
                <path
                  d="M 0 -168 V -58 M -40 -96 L 0 -50 L 40 -96"
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={13}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.92}
                />
              </g>
            </g>
          )}
        </g>
      )}
    </svg>
  );
}

/** Small stand-alone glyph of one piece — used next to the colour name. */
export function PartGlyph({
  part,
  size,
  style,
}: {
  part: KitPart;
  /** Height in px. Omit to fill the parent box. */
  size?: number;
  style?: CSSProperties;
}) {
  const w = partWidth(part);
  const isSlope = part.type === "slope";
  const vbW = w * U + 12;
  const vbH = U + STUD_H + 12;
  const top = STUD_H + 6;
  const bottom = top + U;
  const left = 6;
  const right = left + w * U;
  const fill = fillOf(part.color);
  const d = isSlope
    ? part.high === "right"
      ? `M ${left} ${bottom} L ${right} ${bottom} L ${right} ${top} Z`
      : `M ${left} ${bottom} L ${right} ${bottom} L ${left} ${top} Z`
    : `M ${left + 10} ${top} H ${right - 10} A 10 10 0 0 1 ${right} ${top + 10} V ${bottom - 10}` +
      ` A 10 10 0 0 1 ${right - 10} ${bottom} H ${left + 10} A 10 10 0 0 1 ${left} ${bottom - 10}` +
      ` V ${top + 10} A 10 10 0 0 1 ${left + 10} ${top} Z`;
  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      preserveAspectRatio="xMidYMid meet"
      style={
        size
          ? { height: size, width: (vbW / vbH) * size, ...style }
          : { width: "100%", height: "100%", ...style }
      }
      aria-hidden="true"
    >
      {!isSlope &&
        Array.from({ length: w }).map((_, i) => (
          <rect
            key={i}
            x={left + i * U + (U - STUD_W) / 2}
            y={top - STUD_H}
            width={STUD_W}
            height={STUD_H + 8}
            rx={6}
            fill={fill}
          />
        ))}
      <path d={d} fill={fill} />
      <path d={d} fill="none" stroke="rgba(0,0,0,.3)" strokeWidth={3} />
    </svg>
  );
}

export default BrickFigure;
