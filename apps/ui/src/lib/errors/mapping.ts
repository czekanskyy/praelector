// SPDX-License-Identifier: Apache-2.0
import i18n from "../../i18n";

export function formatErrorCode(code: string): string {
  const parts = code.split(".");
  if (parts.length === 2) {
    const [family, member] = parts;
    const key = `errors:${family}.${member}`;
    if (i18n.exists(key)) {
      return i18n.t(key);
    }
  }

  return i18n.t("errors:generic");
}
