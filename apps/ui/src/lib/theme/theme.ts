// SPDX-License-Identifier: Apache-2.0

export const THEME_STORAGE_KEY = "praelector.theme";

export type ThemeChoice = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export interface MatchMediaLike {
  (query: string): { matches: boolean };
}

const CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return typeof value === "string" && (CHOICES as readonly string[]).includes(value);
}

export function readThemeChoice(
  storage: { getItem(key: string): string | null } | null,
): ThemeChoice {
  if (!storage) return "system";
  const stored = storage.getItem(THEME_STORAGE_KEY);
  return isThemeChoice(stored) ? stored : "system";
}

/** Forced light or dark wins. `system` follows the matchMedia stub or the OS. */
export function resolveTheme(choice: ThemeChoice, matchMedia: MatchMediaLike): ResolvedTheme {
  if (choice === "light" || choice === "dark") return choice;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyThemeClass(
  root: {
    classList: { toggle(token: string, force?: boolean): void };
    style: { colorScheme: string };
  },
  choice: ThemeChoice,
  matchMedia: MatchMediaLike,
): ResolvedTheme {
  const resolved = resolveTheme(choice, matchMedia);
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  return resolved;
}

export function applyInitialTheme(): void {
  if (typeof document === "undefined" || typeof window.matchMedia !== "function") return;
  const storage = typeof localStorage === "undefined" ? null : localStorage;
  applyThemeClass(document.documentElement, readThemeChoice(storage), (query) =>
    window.matchMedia(query),
  );
}
