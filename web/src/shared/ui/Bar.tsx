import { motion, useReducedMotion } from "framer-motion";
import { color, layout, motion as m } from "../theme/tokens";

/** A horizontal bar: `share` of the track, 0 to 1. */
export function Bar({ share, tone, label }: { share: number; tone: string; label: string }) {
  const reduce = useReducedMotion();
  const w = `${Math.max(0, Math.min(1, share)) * 100}%`;
  return (
    <div
      role="img"
      aria-label={label}
      style={{ background: color.skeleton, height: layout.barHeight, borderRadius: layout.radius, overflow: "hidden" }}
    >
      <motion.div
        initial={reduce ? false : { width: 0 }}
        animate={{ width: w }}
        transition={{ duration: m.sheetRise, ease: m.ease }}
        style={{ background: tone, height: "100%" }}
      />
    </div>
  );
}
