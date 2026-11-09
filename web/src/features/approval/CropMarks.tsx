import { motion, useReducedMotion } from "framer-motion";
import { color, layout, motion as m } from "../../shared/theme/tokens";

const L = layout.cropMark;
const G = layout.cropGap;
// one corner: a horizontal and a vertical stroke that stop short of the sheet, as on a printer's proof
const corners = [
  { x: -G, y: -G, sx: -1, sy: -1, h: "left", v: "top" },
  { x: G, y: -G, sx: 1, sy: -1, h: "right", v: "top" },
  { x: -G, y: G, sx: -1, sy: 1, h: "left", v: "bottom" },
  { x: G, y: G, sx: 1, sy: 1, h: "right", v: "bottom" },
] as const;

export function CropMarks() {
  const reduce = useReducedMotion();
  return (
    <>
      {corners.map((c, i) => (
        <svg
          key={i}
          aria-hidden
          width={L}
          height={L}
          style={{
            position: "absolute",
            [c.h]: -L - G,
            [c.v]: -L - G,
            overflow: "visible",
          }}
        >
          {[
            `M ${c.sx > 0 ? 0 : L} ${c.sy > 0 ? 0 : L} H ${c.sx > 0 ? L : 0}`,
            `M ${c.sx > 0 ? 0 : L} ${c.sy > 0 ? 0 : L} V ${c.sy > 0 ? L : 0}`,
          ].map((d, j) => (
            <motion.path
              key={j}
              d={d}
              stroke={color.magenta}
              strokeWidth={layout.rule}
              fill="none"
              initial={reduce ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: m.markDraw, delay: i * m.stagger, ease: m.ease }}
            />
          ))}
        </svg>
      ))}
    </>
  );
}
