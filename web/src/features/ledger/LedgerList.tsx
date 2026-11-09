import type { LedgerEntry } from "../../shared/data/types";
import { color, size, space } from "../../shared/theme/tokens";
import { words } from "../../shared/ui/format";
import { Panel } from "../../shared/ui/Panel";

/** The decision record for this round: who decided what and why, each entry chained to the one before. */
export function LedgerList({ entries, intact }: { entries: LedgerEntry[]; intact: boolean }) {
  return (
    <Panel
      title="Decision record"
      note={intact ? "Hash-chained; the chain verifies, so nothing has been edited or removed." : "The chain does not verify: an entry was changed."}
    >
      {entries.length === 0 ? (
        <p style={{ color: color.inkSoft, fontSize: size.sm }}>No decisions recorded for this round yet.</p>
      ) : (
        <ol style={{ margin: 0, paddingLeft: space.xl, display: "grid", gap: space.sm, fontSize: size.sm }}>
          {entries.map((e) => (
            <li key={e.seq}>
              <strong>{words(e.kind)}</strong> <span style={{ color: color.inkSoft }}>by {words(e.actor).toLowerCase()}</span>
              <div style={{ color: color.inkSoft }}>{e.reason}</div>
              <div style={{ color: color.inkFaint, fontSize: size.xs, fontVariantNumeric: "tabular-nums" }}>{e.hash.slice(0, 16)}</div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
