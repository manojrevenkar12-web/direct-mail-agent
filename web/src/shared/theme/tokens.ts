/** Every colour, size, gap and duration the console uses. Components read these; nothing else is a number. */
export const color = {
  paper: "#F5F7FA",
  sheet: "#FFFFFF",
  ink: "#14213D",
  inkSoft: "#4A5568",
  inkFaint: "#8A94A6",
  rule: "#D5DBE5",
  magenta: "#B0124E", // print-proof magenta: registration marks and the approval
  magentaWash: "#FBEAF0",
  cyan: "#0B7FA6", // what the holdout measures
  cyanWash: "#E3F3F8",
  amber: "#A15C07", // anomalies
  amberWash: "#FBF1E3",
  green: "#1F7A4C", // a check that passed
  greenWash: "#E5F3EC",
  skeleton: "#E6EAF0",
} as const;

export const font = {
  display: "'Archivo Variable', 'Archivo', system-ui, sans-serif",
  body: "'Archivo Variable', 'Archivo', system-ui, sans-serif",
} as const;

/** A modular scale (ratio 1.25) from a 16px base. */
export const size = {
  xs: 12.8,
  sm: 14,
  base: 16,
  md: 20,
  lg: 25,
  xl: 31.25,
  xxl: 39,
  hero: 61,
} as const;

/** Archivo's width axis: expanded for figures, normal for text. */
export const width = { figure: 125, heading: 112, text: 100 } as const;
export const weight = { regular: 400, medium: 500, bold: 700, heavy: 800 } as const;
export const leading = { tight: 1.1, body: 1.55 } as const;

export const space = { xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;

export const layout = {
  maxWidth: 1240,
  sideWidth: 380,
  narrow: 900, // below this the side column moves under the proof
  cropMark: 18,
  cropGap: 6,
  rule: 1,
  radius: 3,
  barHeight: 10,
  chartHeight: 180,
  focusRing: 2,
  figureMin: 160,
  columnMin: 280,
  columnGap: 48,
  cellColumns: "3.5em 1fr 6.5em 5.5em",
  minutesColumns: "1fr 3em",
  barFill: 0.7, // share of a round's column the bar takes
  hairline: 0.3,
} as const;

export const motion = {
  sheetRise: 0.5,
  markDraw: 0.6,
  stagger: 0.06,
  stamp: 0.35,
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  riseOffset: 16,
  pulse: 1.4,
  stampScale: 1.15,
  stampTilt: -3,
} as const;
