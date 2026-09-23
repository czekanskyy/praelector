// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";

import { errorCodeKey, translateError } from "../src/lib/errors";

describe("error codes", () => {
  it("turns dotted engine codes into stable catalogue keys", () => {
    expect(errorCodeKey("ebook.drm_detected")).toBe("ebook_drm_detected");
    expect(errorCodeKey("tts.language_unsupported")).toBe("tts_language_unsupported");
    expect(errorCodeKey("internal.validation_failed")).toBe("internal_validation_failed");
    expect(errorCodeKey("")).toBe("fallback");
  });

  it("uses the generic catalogue entry when the code is unknown", () => {
    const t = (key: string, options?: { code?: string; defaultValue?: string }) => {
      if (key === "errors:ebook_drm_detected") return "drm";
      if (key === "errors:fallback") return `fallback:${options?.code ?? ""}`;
      return options?.defaultValue ?? key;
    };
    expect(translateError(t, "ebook.drm_detected")).toBe("drm");
    expect(translateError(t, "engine.ready_timeout")).toBe("fallback:engine.ready_timeout");
  });
});
