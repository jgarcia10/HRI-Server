import type { KitPart } from "../../lib/kit";
import { colorWord, overlaps, partLayer, partWidth, partX } from "./bricks";

export type PlacementHint = {
  /** One plain sentence: where the piece goes, relative to what is already built. */
  text: string;
  /** Extra orientation line for slopes ("Tall side to the LEFT"), else null. */
  note: string | null;
};

/**
 * Name a brick the participant can pick out of the picture: "the red brick".
 * If several already-placed bricks share that colour, disambiguate by side
 * (left / right) or, when they sit in the same column, by height (lower / upper).
 */
function nameRef(ref: KitPart, placed: KitPart[]): string {
  const word = colorWord(ref.color);
  const sameColor = placed.filter((p) => p.color === ref.color);
  if (sameColor.length <= 1) return `the ${word} brick`;
  const others = sameColor.filter((p) => p !== ref);
  if (others.every((p) => partX(p) > partX(ref))) return `the ${word} brick on the left`;
  if (others.every((p) => partX(p) < partX(ref))) return `the ${word} brick on the right`;
  if (others.every((p) => partLayer(p) < partLayer(ref))) return `the upper ${word} brick`;
  if (others.every((p) => partLayer(p) > partLayer(ref))) return `the lower ${word} brick`;
  return `the ${word} brick`;
}

/** The placed brick that touches the current one on the same layer, if any. */
function sideNeighbour(cur: KitPart, placed: KitPart[]) {
  const x = partX(cur);
  const w = partWidth(cur);
  const layer = partLayer(cur);
  const row = placed.filter((p) => partLayer(p) === layer);
  const right = row.find((p) => partX(p) + partWidth(p) === x); // placed brick is to our left
  if (right) return { ref: right, side: "right" as const };
  const left = row.find((p) => partX(p) === x + w); // placed brick is to our right
  if (left) return { ref: left, side: "left" as const };
  // not touching: fall back to the nearest brick on the same row
  let best: { ref: KitPart; side: "left" | "right" } | null = null;
  let bestGap = Infinity;
  for (const p of row) {
    const gap = partX(p) > x ? partX(p) - (x + w) : x - (partX(p) + partWidth(p));
    if (gap < bestGap) {
      bestGap = gap;
      best = { ref: p, side: partX(p) > x ? "left" : "right" };
    }
  }
  return best;
}

/**
 * Turn the geometry of the next piece into one instruction sentence.
 *
 * Cases covered:
 *  - first piece                     -> "Put it on the table."
 *  - ground level next to a brick    -> "Put it on the table, to the right of the red brick."
 *  - on top of exactly one brick     -> "Put it on top of the blue brick, flush with its left edge."
 *  - bridging two bricks             -> "Put it on top, bridging the blue and the red brick."
 *  - same layer, nothing underneath  -> "Put it next to the lime brick, on its right."
 *  - slopes add                      -> "Tall side to the LEFT."
 */
export function placementHint(parts: KitPart[], step: number): PlacementHint {
  const cur = parts[step];
  if (!cur) return { text: "", note: null };
  const note =
    cur.type === "slope" && (cur.high === "left" || cur.high === "right")
      ? `Tall side to the ${cur.high.toUpperCase()}`
      : null;

  const placed = parts.slice(0, step);
  const x = partX(cur);
  const w = partWidth(cur);
  const layer = partLayer(cur);

  if (placed.length === 0) return { text: "Put it on the table.", note };

  if (layer === 0) {
    const n = sideNeighbour(cur, placed);
    if (!n) return { text: "Put it on the table.", note };
    return {
      text: `Put it on the table, to the ${n.side} of ${nameRef(n.ref, placed)}.`,
      note,
    };
  }

  const supports = placed
    .filter((p) => partLayer(p) === layer - 1 && overlaps(x, w, partX(p), partWidth(p)))
    .sort((a, b) => partX(a) - partX(b));

  if (supports.length === 0) {
    const n = sideNeighbour(cur, placed);
    if (!n) return { text: "Put it on top of the figure.", note };
    return {
      text: `Put it next to ${nameRef(n.ref, placed)}, on its ${n.side === "right" ? "right" : "left"}.`,
      note,
    };
  }

  if (supports.length >= 2) {
    const a = supports[0];
    const b = supports[supports.length - 1];
    if (a.color === b.color && supports.every((p) => p.color === a.color)) {
      return { text: `Put it on top, bridging the two ${colorWord(a.color)} bricks.`, note };
    }
    return {
      text: `Put it on top, bridging the ${colorWord(a.color)} and the ${colorWord(b.color)} brick.`,
      note,
    };
  }

  const s = supports[0];
  const sx = partX(s);
  const sw = partWidth(s);
  const name = nameRef(s, placed);
  let clause = "";
  if (sx === x && sw === w) {
    clause = "";
  } else if (sx === x) {
    clause = ", flush with its left edge";
  } else if (sx + sw === x + w) {
    clause = ", flush with its right edge";
  } else if (Math.abs(x + w / 2 - (sx + sw / 2)) < 1e-6) {
    clause = ", right in the middle";
  } else if (x + w / 2 < sx + sw / 2) {
    clause = ", on its left half";
  } else {
    clause = ", on its right half";
  }

  if (clause === "") {
    const n = sideNeighbour(cur, placed);
    if (n) {
      return {
        text: `Put it on top of ${name}, next to ${nameRef(n.ref, placed)}.`,
        note,
      };
    }
  }
  return { text: `Put it on top of ${name}${clause}.`, note };
}
