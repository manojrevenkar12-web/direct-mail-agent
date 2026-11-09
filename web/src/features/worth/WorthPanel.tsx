import type { ConsoleData } from "../../shared/data/types";
import { color, layout, size, space, weight } from "../../shared/theme/tokens";
import { Bar } from "../../shared/ui/Bar";
import { Figure } from "../../shared/ui/Figure";
import { gbp, pct } from "../../shared/ui/format";
import { Panel } from "../../shared/ui/Panel";

/** What mail is worth, measured two ways against the simulated truth, and how the policies compare. */
export function WorthPanel({ d }: { d: ConsoleData }) {
  const held = d.agent.measured_vs_true ?? 0;
  const match = d.agent.matchback_vs_true ?? 0;
  const top = Math.max(match, held, 1);
  const best = Math.max(...d.policies.map((p) => p.profit));
  const most = Math.max(...d.policies.map((p) => p.minutes));
  const shown = d.policies.filter((p) => ["today", "for_loop", "agent", "agent_no_holdout", "unguarded_llm"].includes(p.id));
  const short: Record<string, string> = {
    today: "Today's process",
    for_loop: "For-loop, no model",
    agent: "The agent",
    agent_no_holdout: "Agent, no holdout",
    unguarded_llm: "Model without checks",
  };
  return (
    <>
      <Panel
        title="What mail was worth"
        note="Applications the letters caused over a year, as each method counts them. 1.0 is the truth."
      >
        <div style={{ display: "grid", gap: space.md }}>
          {[
            { label: "Mailed against a 5% random holdout", v: held, tone: color.cyan },
            { label: "Every application from a mailed business", v: match, tone: color.inkFaint },
          ].map((x) => (
            <div key={x.label}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: size.sm }}>
                <span>{x.label}</span>
                <strong style={{ fontVariantNumeric: "tabular-nums" }}>{x.v.toFixed(2)}×</strong>
              </div>
              <Bar share={x.v / top} tone={x.tone} label={`${x.label}: ${x.v.toFixed(2)} times the truth`} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Against today's process"
        note={`Held-out market, ${d.seeds} seeds, 12 monthly rounds, same budget. Incremental profit after postage.`}
      >
        <div style={{ display: "grid", gap: space.md }}>
          {shown.map((p) => (
            <div key={p.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, fontSize: size.sm }}>
                <span style={{ fontWeight: p.id === "agent" ? weight.bold : weight.regular }}>{short[p.id]}</span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {gbp(p.profit)} {p.id !== "today" && <span style={{ color: color.inkSoft }}>{pct(p.vs_today)}</span>}
                </span>
              </div>
              <Bar share={p.profit / best} tone={p.id === "agent" ? color.magenta : color.ink} label={`${short[p.id]}: ${gbp(p.profit)}`} />
              {p.breaches > 0 && (
                <div style={{ fontSize: size.xs, color: color.magenta }}>
                  {Math.round(p.breaches).toLocaleString("en-GB")} letters a year to businesses that objected, are registered
                  with the Mailing Preference Service or have gone away
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="A person's time, each round" note="Minutes, from the same assumptions for every policy.">
        <div style={{ display: "grid", gap: space.md }}>
          {shown.filter((p) => p.id !== "agent_no_holdout").map((p) => (
            <div key={p.id} style={{ display: "grid", gridTemplateColumns: layout.minutesColumns, gap: space.sm, alignItems: "center", fontSize: size.sm }}>
              <div>
                {short[p.id]}
                <Bar share={p.minutes / most} tone={color.inkSoft} label={`${short[p.id]}: ${Math.round(p.minutes)} minutes`} />
              </div>
              <strong style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{Math.round(p.minutes)}</strong>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="The model's part" note="Means a year on the held-out market.">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: space.lg }}>
          <Figure value={`${((d.agent.model_read_correct ?? 0) * 100).toFixed(1)}%`} label="emails read right first time" />
          <Figure value={`${(d.agent.directions_stopped ?? 0).toFixed(1)}`} label="wrong directions stopped by code" />
          <Figure value={`${(d.agent.anomaly_real_detected ?? 0).toFixed(1)}`} label="incidents caught" tone={color.amber} />
          <Figure value={`£${(d.agent.llm_gbp_per_round ?? 0).toFixed(2)}`} label="model cost a round" />
        </div>
      </Panel>
    </>
  );
}
