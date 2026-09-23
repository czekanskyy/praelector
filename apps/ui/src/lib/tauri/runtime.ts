// SPDX-License-Identifier: Apache-2.0

/** True only inside the Tauri webview. A plain Vite tab has neither global. */
export function inTauriWebview(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
}
