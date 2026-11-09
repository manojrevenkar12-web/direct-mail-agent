import { ProofSheet } from "./features/approval/ProofSheet";
import { LedgerList } from "./features/ledger/LedgerList";
import { RoundsChart } from "./features/rounds/RoundsChart";
import { WorthPanel } from "./features/worth/WorthPanel";
import { useConsole } from "./shared/data/useConsole";
import { color, layout, size, space } from "./shared/theme/tokens";
import { ErrorState, Skeleton } from "./shared/ui/states";
import { useNarrow } from "./shared/ui/useNarrow";

export default function App({ url }: { url?: string }) {
  const [load, retry] = useConsole(url);
  const narrow = useNarrow(layout.narrow);
  return (
    <main style={{ maxWidth: layout.maxWidth, margin: "0 auto", padding: `${space.xxl}px ${space.lg}px` }}>
      <p style={{ margin: `0 0 ${space.lg}px`, color: color.inkSoft, fontSize: size.sm }}>
        Direct-mail round approval. The agent planned this round; code checked it; it prints only if you approve it.
      </p>
      {load.state === "loading" && <Skeleton />}
      {load.state === "error" && <ErrorState message={load.message} onRetry={retry} />}
      {load.state === "ready" && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: narrow ? "minmax(0, 1fr)" : `minmax(0, 1fr) ${layout.sideWidth}px`,
            gap: layout.columnGap,
            alignItems: "start",
          }}
        >
          <div>
            <ProofSheet s={load.data.sample} />
            <RoundsChart rounds={load.data.rounds} />
            <LedgerList entries={load.data.sample.ledger} intact={load.data.sample.ledger_intact} />
          </div>
          <aside>
            <WorthPanel d={load.data} />
          </aside>
        </div>
      )}
    </main>
  );
}
