import { motion, useReducedMotion } from "framer-motion";
import { color, font, layout, motion as motion_, size, space, weight, width } from "../theme/tokens";

const block = (h: number, w: string) => ({ height: h, width: w, background: color.skeleton, borderRadius: layout.radius });

/** The page's shape while the data loads, so nothing jumps when it arrives. */
export function Skeleton() {
  const reduce = useReducedMotion();
  const pulse = reduce ? {} : { animate: { opacity: [1, 0.55, 1] }, transition: { duration: motion_.pulse, repeat: Infinity } };
  return (
    <motion.div aria-busy="true" aria-label="Loading the round" {...pulse} style={{ display: "grid", gap: space.lg }}>
      <div style={block(size.xxl, "40%")} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: space.lg }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={block(size.hero, "100%")} />
        ))}
      </div>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={block(size.base, `${90 - i * 12}%`)} />
      ))}
    </motion.div>
  );
}

const box = {
  border: `${layout.rule}px solid ${color.rule}`,
  background: color.sheet,
  padding: space.xxl,
  borderRadius: layout.radius,
};
const title = {
  fontFamily: font.display,
  fontVariationSettings: `"wdth" ${width.heading}`,
  fontWeight: weight.bold,
  fontSize: size.md,
  margin: `0 0 ${space.sm}px`,
};

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" style={box}>
      <h2 style={title}>The round could not be loaded</h2>
      <p style={{ margin: `0 0 ${space.lg}px`, color: color.inkSoft }}>
        {message} Nothing has been approved or sent. Load it again, or check the results service.
      </p>
      <button
        onClick={onRetry}
        style={{
          background: color.ink,
          color: color.sheet,
          border: 0,
          padding: `${space.sm}px ${space.lg}px`,
          borderRadius: layout.radius,
          cursor: "pointer",
        }}
      >
        Load again
      </button>
    </div>
  );
}

export function EmptyState({ title: t, body }: { title: string; body: string }) {
  return (
    <div style={box}>
      <h2 style={title}>{t}</h2>
      <p style={{ margin: 0, color: color.inkSoft }}>{body}</p>
    </div>
  );
}
