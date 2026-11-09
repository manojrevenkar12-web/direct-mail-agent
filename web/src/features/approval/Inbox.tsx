import type { Anomaly, Direction } from "../../shared/data/types";
import { color, layout, size, space } from "../../shared/theme/tokens";
import { words } from "../../shared/ui/format";

const row = (tone: string) => ({
  borderLeft: `${layout.focusRing}px solid ${tone}`,
  padding: `${space.xs}px ${space.md}px`,
  fontSize: size.sm,
});

/** What the model read in the team mailbox, and what code did with it. */
export function Directions({ items }: { items: Direction[] }) {
  if (!items.length) return <p style={{ color: color.inkSoft, fontSize: size.sm }}>No directions this round.</p>;
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      {items.map((d, i) => (
        <div key={i} style={row(d.applied ? color.green : color.inkFaint)}>
          <strong>{d.kind === "route" ? "Passed on" : d.applied ? "Applied" : "Not applied"}</strong>{" "}
          {d.kind === "route" ? d.why : words(d.kind).toLowerCase()}
          {d.sender && <span style={{ color: color.inkSoft }}> from {d.sender}</span>}
          {d.quote && <div style={{ color: color.inkSoft }}>“{d.quote}”</div>}
          {!d.applied && d.kind !== "route" && <div style={{ color: color.magenta }}>{d.why}</div>}
        </div>
      ))}
    </div>
  );
}

export function Anomalies({ items }: { items: Anomaly[] }) {
  if (!items.length) return <p style={{ color: color.inkSoft, fontSize: size.sm }}>Nothing unusual in the results.</p>;
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      {items.map((a, i) => (
        <div key={i} style={{ ...row(color.amber), background: color.amberWash }}>
          <strong>{words(a.anomaly)}</strong>
          {a.cause && a.cause !== "noise"
            ? `: likely ${words(a.cause).toLowerCase()}, sent to ${words(a.owner_role).toLowerCase()}`
            : ": within normal variation, so nobody was asked to look"}
        </div>
      ))}
    </div>
  );
}
