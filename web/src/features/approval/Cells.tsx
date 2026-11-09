import type { CellPlan } from "../../shared/data/types";
import { color, layout, size, space } from "../../shared/theme/tokens";
import { Bar } from "../../shared/ui/Bar";
import { gbp2, n } from "../../shared/ui/format";

/** Where the letters go: response band (b1 lowest) by value tier, with the value each letter is expected to add. */
export function Cells({ cells }: { cells: CellPlan[] }) {
  const most = Math.max(1, ...cells.map((c) => c.letters));
  return (
    <div style={{ display: "grid", gap: space.xs }}>
      {cells.map((c) => (
        <div
          key={c.cell}
          style={{ display: "grid", gridTemplateColumns: layout.cellColumns, gap: space.sm, alignItems: "center", fontSize: size.sm }}
        >
          <span style={{ color: color.inkSoft }}>{c.cell}</span>
          <Bar share={c.letters / most} tone={color.ink} label={`${c.cell}: ${n(c.letters)} letters`} />
          <span style={{ fontVariantNumeric: "tabular-nums", textAlign: "right" }}>{n(c.letters)}</span>
          <span style={{ fontVariantNumeric: "tabular-nums", textAlign: "right", color: color.inkSoft }}>
            {gbp2(c.value_per_letter)}
          </span>
        </div>
      ))}
    </div>
  );
}
