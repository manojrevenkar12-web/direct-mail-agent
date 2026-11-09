import type { Check } from "../../shared/data/types";
import { color, layout, size, space } from "../../shared/theme/tokens";
import { words } from "../../shared/ui/format";

const NAMES: Record<string, string> = {
  suppressions: "Nobody suppressed is mailed",
  budget: "Within budget and the cap",
  capacity: "Within the print house's capacity",
  creatives_approved: "Every letter approved by compliance",
  excluded_sectors: "Excluded sectors left out",
  no_duplicates: "No business twice",
  matches_plan: "The file is the plan",
  holdout: "Every mailed cell has its holdout",
};

/** The checks code ran on the file, before anyone was asked. */
export function Preflight({ checks }: { checks: Check[] }) {
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.xs }}>
      {checks.map((c) => (
        <li
          key={c.check}
          title={c.detail}
          style={{
            display: "grid",
            gridTemplateColumns: `${size.base}px 1fr`,
            gap: space.sm,
            alignItems: "baseline",
            padding: `${space.xs}px ${space.sm}px`,
            background: c.passed ? color.greenWash : color.magentaWash,
            borderRadius: layout.radius,
            fontSize: size.sm,
          }}
        >
          <span aria-hidden style={{ color: c.passed ? color.green : color.magenta }}>
            {c.passed ? "✓" : "✕"}
          </span>
          <span>
            {NAMES[c.check] ?? words(c.check)}
            {!c.passed && <span style={{ color: color.inkSoft }}>: {c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
