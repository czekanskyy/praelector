// SPDX-License-Identifier: Apache-2.0

export interface ErrorTranslator {
  (key: string, options?: { code?: string; defaultValue?: string }): string;
}

/**
 * Dots are i18next's nesting separator, so `ebook.drm_detected` becomes the
 * flat catalogue key `ebook_drm_detected`. The `errors:${…}` template is what
 * `scripts/i18n_check.mjs` treats as a dynamic namespace (D-16).
 */
export function errorCodeKey(code: string): string {
  const stable = code
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return stable.length > 0 ? stable : "fallback";
}

export function translateError(t: ErrorTranslator, code: string): string {
  const key = errorCodeKey(code);
  return t(`errors:${key}`, {
    code,
    defaultValue: t("errors:fallback", { code }),
  });
}
