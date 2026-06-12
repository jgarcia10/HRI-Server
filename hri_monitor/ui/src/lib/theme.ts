import { useCallback, useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "hri-theme";

function systemTheme(): "light" | "dark" {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system"; // private mode: no persistence, system default
  }
}

/** Theme preference cycle: light → dark → system. "system" tracks the OS live. */
export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(storedPref);
  const [sys, setSys] = useState<"light" | "dark">(systemTheme);
  const resolved = pref === "system" ? sys : pref;

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSys(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    try {
      if (pref === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, pref);
    } catch {
      // private mode: theme applies but won't persist
    }
  }, [pref, resolved]);

  const cycle = useCallback(() => {
    setPref((p) => (p === "light" ? "dark" : p === "dark" ? "system" : "light"));
  }, []);

  return { pref, resolved, cycle };
}
