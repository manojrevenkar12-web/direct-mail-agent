import "@fontsource-variable/archivo/wdth.css";
import "./shared/theme/global.css";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { color, font, layout, leading, size } from "./shared/theme/tokens";

// the tokens become CSS variables for the few rules that live in CSS
const root = document.documentElement.style;
Object.entries(color).forEach(([k, v]) => root.setProperty(`--${k}`, v));
root.setProperty("--font-body", font.body);
root.setProperty("--size-base", `${size.base}px`);
root.setProperty("--leading-body", String(leading.body));
root.setProperty("--focus-ring", `${layout.focusRing}px`);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
