const gb = new Intl.NumberFormat("en-GB");
const money = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const date = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

export const n = (x: number) => gb.format(Math.round(x));
const pence = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", minimumFractionDigits: 2 });
export const gbp = (x: number) => money.format(x);
export const gbp2 = (x: number) => pence.format(x);
export const pct = (x: number, digits = 1) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
export const day = (iso: string) => date.format(new Date(`${iso}T12:00:00`));
export const words = (id: string) => id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
