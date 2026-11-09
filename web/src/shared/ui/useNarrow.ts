import { useEffect, useState } from "react";

/** True while the viewport is at most `px` wide. */
export function useNarrow(px: number): boolean {
  const query = `(max-width: ${px}px)`;
  const get = () => typeof window !== "undefined" && !!window.matchMedia?.(query).matches;
  const [narrow, setNarrow] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return narrow;
}
