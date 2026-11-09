import { useCallback, useEffect, useState } from "react";
import type { ConsoleData } from "./types";

export type Load<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

/** Loads the console's data; `retry` loads it again after an error. */
export function useConsole(url = "./data/console.json"): [Load<ConsoleData>, () => void] {
  const [load, setLoad] = useState<Load<ConsoleData>>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoad({ state: "loading" });
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`The results service answered ${r.status}.`);
        return r.json() as Promise<ConsoleData>;
      })
      .then((data) => live && setLoad({ state: "ready", data }))
      .catch((e: Error) => live && setLoad({ state: "error", message: e.message }));
    return () => {
      live = false;
    };
  }, [url, attempt]);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return [load, retry];
}
