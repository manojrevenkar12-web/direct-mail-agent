import type { ReactNode } from "react";
import { color, font, layout, size, space, weight, width } from "../theme/tokens";

export function Heading({ children, as: As = "h2" }: { children: ReactNode; as?: "h2" | "h3" }) {
  const big = As === "h2";
  return (
    <As
      style={{
        fontFamily: font.display,
        fontVariationSettings: `"wdth" ${width.heading}`,
        fontWeight: weight.bold,
        fontSize: big ? size.md : size.base,
        margin: `0 0 ${space.md}px`,
        color: color.ink,
      }}
    >
      {children}
    </As>
  );
}

export function Panel({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section style={{ borderTop: `${layout.rule}px solid ${color.rule}`, paddingTop: space.lg, marginTop: space.xl }}>
      <Heading>{title}</Heading>
      {note && <p style={{ margin: `-${space.sm}px 0 ${space.md}px`, color: color.inkSoft, fontSize: size.sm }}>{note}</p>}
      {children}
    </section>
  );
}
