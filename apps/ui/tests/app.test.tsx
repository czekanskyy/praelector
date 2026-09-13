// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from "vitest";
import { formatErrorCode } from "../src/lib/errors/mapping";
import "../src/i18n";

describe("UI error mapping and i18n", () => {
  it("translates known error code to localized message", () => {
    const msg = formatErrorCode("ebook.drm_detected");
    expect(msg).toContain("DRM");
  });

  it("translates unauthorized auth error", () => {
    const msg = formatErrorCode("auth.unauthorized");
    expect(msg).toContain("Authentication failed");
  });

  it("falls back to generic error on unknown code", () => {
    const msg = formatErrorCode("unknown.error.code");
    expect(msg).toBe("An unknown error occurred.");
  });
});
