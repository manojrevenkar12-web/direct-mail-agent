import { color, font, leading, size, space, weight, width } from "../theme/tokens";

/** A figure set wide and heavy, with what it counts underneath. */
export function Figure({ value, label, tone = color.ink }: { value: string; label: string; tone?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontFamily: font.display,
          fontVariationSettings: `"wdth" ${width.figure}`,
          fontWeight: weight.heavy,
          fontSize: size.xl,
          lineHeight: leading.tight,
          fontVariantNumeric: "tabular-nums",
          color: tone,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: size.sm, color: color.inkSoft, marginTop: space.xs }}>{label}</div>
    </div>
  );
}
