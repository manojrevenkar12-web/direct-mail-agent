import type { RoundRow } from "../../shared/data/types";
import { color, layout, size, space } from "../../shared/theme/tokens";
import { Panel } from "../../shared/ui/Panel";

/** Funded loans per round: the ones the letters caused, inside the ones matchback would credit to mail. */
export function RoundsChart({ rounds }: { rounds: RoundRow[] }) {
  const H = layout.chartHeight;
  const top = Math.max(1, ...rounds.map((r) => r.attributed_funded));
  const col = 100 / rounds.length;
  return (
    <Panel
      title="Funded loans, round by round"
      note="Outline: every funded loan from a mailed business. Filled: the ones the letters caused (the simulated truth)."
    >
      <svg role="img" aria-label="Funded loans per round" viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }}>
        {rounds.map((r, i) => {
          const w = col * layout.barFill;
          const x = i * col + (col - w) / 2;
          const ha = (r.attributed_funded / top) * (H - size.base);
          const hc = (r.mail_caused_funded / top) * (H - size.base);
          return (
            <g key={r.round}>
              <rect x={x} y={H - ha} width={w} height={ha} fill="none" stroke={color.inkFaint} strokeWidth={layout.hairline} vectorEffect="non-scaling-stroke" />
              <rect x={x} y={H - hc} width={w} height={hc} fill={color.magenta} />
            </g>
          );
        })}
      </svg>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${rounds.length}, 1fr)`, fontSize: size.xs, color: color.inkSoft, textAlign: "center", marginTop: space.xs }}>
        {rounds.map((r) => (
          <span key={r.round}>{r.paused ? "paused" : r.round}</span>
        ))}
      </div>
    </Panel>
  );
}
