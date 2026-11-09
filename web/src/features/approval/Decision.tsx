import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { color, font, layout, motion as m, size, space, weight, width } from "../../shared/theme/tokens";

type State = "open" | "approved" | "sent_back";

/** Approve sends this exact file (by its hash) to the print house; send back asks the agent to plan again. */
export function Decision({ sha, ready }: { sha: string; ready: boolean }) {
  const [state, setState] = useState<State>("open");
  const reduce = useReducedMotion();
  const button = (primary: boolean) => ({
    background: primary ? color.magenta : "transparent",
    color: primary ? color.sheet : color.ink,
    border: `${layout.rule}px solid ${primary ? color.magenta : color.rule}`,
    padding: `${space.sm}px ${space.xl}px`,
    borderRadius: layout.radius,
    cursor: ready ? "pointer" : "not-allowed",
    fontWeight: weight.bold,
  });
  return (
    <div style={{ display: "flex", gap: space.md, alignItems: "center", flexWrap: "wrap", minHeight: size.hero }}>
      <AnimatePresence mode="wait">
        {state === "open" ? (
          <motion.div key="open" exit={{ opacity: 0 }} style={{ display: "flex", gap: space.md, flexWrap: "wrap" }}>
            <button disabled={!ready} style={button(true)} onClick={() => setState("approved")}>
              Approve for print
            </button>
            <button disabled={!ready} style={button(false)} onClick={() => setState("sent_back")}>
              Send back
            </button>
          </motion.div>
        ) : (
          <motion.div
            key="done"
            role="status"
            initial={reduce ? false : { scale: m.stampScale, opacity: 0, rotate: m.stampTilt }}
            animate={{ scale: 1, opacity: 1, rotate: m.stampTilt }}
            transition={{ duration: m.stamp, ease: m.ease }}
            style={{
              border: `${layout.focusRing}px solid ${state === "approved" ? color.magenta : color.inkSoft}`,
              color: state === "approved" ? color.magenta : color.inkSoft,
              padding: `${space.xs}px ${space.lg}px`,
              fontFamily: font.display,
              fontVariationSettings: `"wdth" ${width.figure}`,
              fontWeight: weight.heavy,
              fontSize: size.md,
            }}
          >
            {state === "approved" ? "Approved for print" : "Sent back to the agent"}
          </motion.div>
        )}
      </AnimatePresence>
      <span style={{ fontSize: size.xs, color: color.inkFaint }}>
        {state === "approved"
          ? `Released as file ${sha.slice(0, 12)}. A changed file would need a new approval.`
          : `Demo: the decision stays in this page. In production it goes to the approval API with your SSO identity.`}
      </span>
    </div>
  );
}
