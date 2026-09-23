// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  applyThemeClass,
  readThemeChoice,
  THEME_STORAGE_KEY,
  type ThemeChoice,
} from "../../lib/theme/theme";

interface ThemeContextValue {
  choice: ThemeChoice;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemIsDark(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeRoot({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(() =>
    readThemeChoice(typeof localStorage === "undefined" ? null : localStorage),
  );
  const [systemDark, setSystemDark] = useState(systemIsDark);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemDark(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    applyThemeClass(document.documentElement, choice, (query) => window.matchMedia(query));
    try {
      localStorage.setItem(THEME_STORAGE_KEY, choice);
    } catch {
      // Private mode can reject storage; the in-memory choice still paints.
    }
  }, [choice, systemDark]);

  const value = useMemo(() => ({ choice, setChoice }), [choice]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeChoice(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("theme");
  return value;
}
