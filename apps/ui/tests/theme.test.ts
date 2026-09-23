// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";

import { resolveTheme, type MatchMediaLike } from "../src/lib/theme/theme";

function matchMedia(matches: boolean): MatchMediaLike {
  return (query) => {
    expect(query).toBe("(prefers-color-scheme: dark)");
    return { matches };
  };
}

describe("resolveTheme", () => {
  it("follows the matchMedia stub when the choice is system", () => {
    expect(resolveTheme("system", matchMedia(true))).toBe("dark");
    expect(resolveTheme("system", matchMedia(false))).toBe("light");
  });

  it("ignores the OS when the choice is forced", () => {
    expect(resolveTheme("light", matchMedia(true))).toBe("light");
    expect(resolveTheme("dark", matchMedia(false))).toBe("dark");
  });
});
