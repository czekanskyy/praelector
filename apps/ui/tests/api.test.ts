// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";

import { EngineApi } from "../src/lib/api/client";
import { EngineRequestError, failureCode, parseEngineEndpoint } from "../src/lib/api/endpoint";

const TOKEN = "aaaaaaaaaaaaaaaa";

describe("engine endpoint", () => {
  it("accepts a port or the shell base URL", () => {
    expect(parseEngineEndpoint({ port: 1420, token: TOKEN })).toEqual({
      port: 1420,
      token: TOKEN,
    });
    expect(parseEngineEndpoint({ baseUrl: "http://127.0.0.1:4312", token: TOKEN })).toEqual({
      port: 4312,
      token: TOKEN,
    });
  });

  it("rejects a non-loopback base URL", () => {
    expect(() => parseEngineEndpoint({ baseUrl: "http://localhost:9", token: TOKEN })).toThrow(
      EngineRequestError,
    );
  });

  it("reads a stable code off a command rejection", () => {
    expect(failureCode({ code: "engine.not_ready" })).toBe("engine.not_ready");
    expect(failureCode(new EngineRequestError("ebook.drm_detected"))).toBe("ebook.drm_detected");
    expect(failureCode(new Error("nope"))).toBe("engine.not_ready");
  });
});

describe("EngineApi", () => {
  it("calls loopback with a bearer token and no Origin header", async () => {
    const seen: { url: string; authorization: string | null; origin: string | null }[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const headers = new Headers(init?.headers);
      seen.push({
        url: String(input),
        authorization: headers.get("Authorization"),
        origin: headers.get("Origin"),
      });
      return new Response(JSON.stringify([]), { status: 200 });
    };
    const api = new EngineApi({ port: 9, token: TOKEN }, fetchImpl);
    await expect(api.eventsSince(4)).resolves.toEqual([]);
    expect(seen).toEqual([
      {
        url: "http://127.0.0.1:9/v1/events?since=4",
        authorization: `Bearer ${TOKEN}`,
        origin: null,
      },
    ]);
  });
});
