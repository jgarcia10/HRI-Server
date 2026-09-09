import type { KitPart } from "../../lib/kit";

/** Physical brick colours (as printed on the real MEGA BLOKS pieces). */
export const BRICK_FILL: Record<string, string> = {
  red: "#d64541",
  orange: "#e67e22",
  blue: "#2e86de",
  seafoam: "#7fd6c2",
  lime: "#a3cb38",
};

/** Same hues, lifted for legibility as text on a dark background. */
export const BRICK_TEXT: Record<string, string> = {
  red: "#ff7a6e",
  orange: "#ffab4f",
  blue: "#5aa9ff",
  seafoam: "#9fe8d8",
  lime: "#c6e75c",
};

/** Plain words a participant can say out loud. No jargon, no codes. */
const COLOR_WORD: Record<string, string> = {
  red: "red",
  orange: "orange",
  blue: "blue",
  seafoam: "mint",
  lime: "lime",
};

const SHAPE_WORD: Record<string, string> = {
  "1x2": "long brick",
  "1x1": "small brick",
  slope: "roof piece",
};

export const colorWord = (c: string) => COLOR_WORD[c] ?? c;
export const shapeWord = (t: string) => SHAPE_WORD[t] ?? "brick";
export const fillOf = (c: string) => BRICK_FILL[c] ?? "#94a3b8";
export const textOf = (c: string) => BRICK_TEXT[c] ?? "#cbd5e1";

/** Width in studs. `width` comes from the hub; the type is the fallback. */
export const partWidth = (p: Pick<KitPart, "type" | "width">) =>
  p.width && p.width > 0 ? p.width : p.type === "1x2" ? 2 : 1;

export const partX = (p: KitPart) => p.pos[0];
export const partLayer = (p: KitPart) => p.pos[1];

/** Horizontal overlap of two [x, x+w) spans. */
export const overlaps = (a: number, aw: number, b: number, bw: number) =>
  a < b + bw && b < a + aw;

/** Studs hidden by whatever sits on the cell above are not drawn. */
export function occupiedCells(parts: KitPart[]): Set<string> {
  const cells = new Set<string>();
  for (const p of parts) {
    const w = partWidth(p);
    for (let i = 0; i < w; i++) cells.add(`${partX(p) + i},${partLayer(p)}`);
  }
  return cells;
}

/** Bounding size of a figure in studs / layers (fallback when width_studs is 0). */
export function figureSize(parts: KitPart[], widthStuds: number) {
  let w = widthStuds > 0 ? widthStuds : 1;
  let h = 1;
  for (const p of parts) {
    w = Math.max(w, partX(p) + partWidth(p));
    h = Math.max(h, partLayer(p) + 1);
  }
  return { studs: w, layers: h };
}
