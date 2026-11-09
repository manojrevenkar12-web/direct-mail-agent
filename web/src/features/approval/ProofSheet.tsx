import { motion, useReducedMotion } from "framer-motion";
import type { Sample } from "../../shared/data/types";
import { color, font, layout, leading, motion as m, size, space, weight, width } from "../../shared/theme/tokens";
import { day, gbp, n, words } from "../../shared/ui/format";
import { Figure } from "../../shared/ui/Figure";
import { EmptyState } from "../../shared/ui/states";
import { Heading } from "../../shared/ui/Panel";
import { Cells } from "./Cells";
import { CropMarks } from "./CropMarks";
import { Decision } from "./Decision";
import { Anomalies, Directions } from "./Inbox";
import { Preflight } from "./Preflight";

/** The round waiting for a decision, laid out like a printer's proof: what will be sent, and why. */
export function ProofSheet({ s }: { s: Sample }) {
  const reduce = useReducedMotion();
  if (s.plan.paused || s.plan.letters === 0) {
    return (
      <EmptyState
        title={`Round ${s.round} is paused`}
        body="Nothing will be printed this round, so there is nothing to approve. The next round will be planned on schedule."
      />
    );
  }
  const allPassed = s.checks.every((c) => c.passed);
  const shares = Object.entries(s.plan.creative_shares)
    .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`)
    .join(", ");
  return (
    <motion.article
      initial={reduce ? false : { opacity: 0, y: m.riseOffset }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: m.sheetRise, ease: m.ease }}
      style={{
        position: "relative",
        background: color.sheet,
        border: `${layout.rule}px solid ${color.rule}`,
        padding: space.xxl,
        margin: layout.cropMark + layout.cropGap,
      }}
    >
      <CropMarks />
      <header style={{ display: "flex", justifyContent: "space-between", gap: space.lg, flexWrap: "wrap" }}>
        <div>
          <h1
            style={{
              fontFamily: font.display,
              fontVariationSettings: `"wdth" ${width.figure}`,
              fontWeight: weight.heavy,
              fontSize: size.xxl,
              margin: 0,
              lineHeight: leading.tight,
            }}
          >
            Round {s.round}
          </h1>
          <p style={{ margin: `${space.xs}px 0 0`, color: color.inkSoft }}>
            Lands on doormats on {day(s.drop_date)}. File {s.sha256.slice(0, 12)}, {allPassed ? "every check passed" : "checks failed"}.
          </p>
        </div>
        <Decision sha={s.sha256} ready={allPassed} />
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(auto-fit, minmax(${layout.figureMin}px, 1fr))`,
          gap: space.xl,
          margin: `${space.xl}px 0`,
        }}
      >
        <Figure value={n(s.plan.letters)} label="letters" />
        <Figure value={n(s.plan.holdout)} label={`held out (${(s.plan.holdout_share * 100).toFixed(0)}%) to measure what mail adds`} tone={color.cyan} />
        <Figure value={gbp(s.plan.cost)} label={`of a ${gbp(s.plan.budget)} budget`} />
        <Figure value={gbp(s.plan.expected_incremental_value)} label="expected incremental funded value" />
      </div>

      {s.brief && (
        <blockquote
          style={{
            margin: `0 0 ${space.xl}px`,
            padding: `${space.md}px ${space.lg}px`,
            borderLeft: `${layout.focusRing}px solid ${color.ink}`,
            background: color.paper,
            whiteSpace: "pre-line",
          }}
        >
          {s.brief}
          <footer style={{ fontSize: size.xs, color: color.inkFaint, marginTop: space.sm }}>
            Written by the model; every figure checked against the plan by code.
          </footer>
        </blockquote>
      )}

      <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${layout.columnMin}px, 1fr))`, gap: space.xxl }}>
        <div>
          <Heading as="h3">Checks code ran on the file</Heading>
          <Preflight checks={s.checks} />
        </div>
        <div>
          <Heading as="h3">Where the letters go</Heading>
          <Cells cells={s.plan.cells} />
          <p style={{ fontSize: size.xs, color: color.inkFaint, margin: `${space.sm}px 0 0` }}>
            Response band b1 (lowest) to b5, value tier v1 or v2; right, the value a letter is expected to add. Letters:{" "}
            {shares}.{s.plan.excluded_sectors.length ? ` Left out: ${s.plan.excluded_sectors.map(words).join(", ")}.` : ""}
          </p>
        </div>
        <div>
          <Heading as="h3">From the team mailbox</Heading>
          <Directions items={s.directions} />
        </div>
        <div>
          <Heading as="h3">In the results</Heading>
          <Anomalies items={s.anomalies} />
        </div>
      </div>
    </motion.article>
  );
}
