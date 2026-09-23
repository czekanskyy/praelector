// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";

import { EngineApi } from "../src/lib/api/client";
import { EngineEvents, type MinimalSocket } from "../src/lib/ws/client";
import { gapSince } from "../src/lib/ws/gap";

const TOKEN = "aaaaaaaaaaaaaaaa";

describe("gapSince", () => {
  it("reports a hole and ignores the next number and duplicates", () => {
    expect(gapSince(2, 3)).toBeNull();
    expect(gapSince(2, 2)).toBeNull();
    expect(gapSince(2, 4)).toBe(2);
  });
});

describe("EngineEvents", () => {
  it("fills a seq hole through the api client and a fake socket", async () => {
    const seen: string[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
      expect(headers.get("Origin")).toBeNull();
      seen.push(String(input));
      return new Response(JSON.stringify([{ seq: 3, type: "job.state" }]), { status: 200 });
    };
    const api = new EngineApi({ port: 9, token: TOKEN }, fetchImpl);
    let socket!: MinimalSocket;
    const events = new EngineEvents({ port: 9, token: TOKEN }, api, (url) => {
      expect(url).toBe(`ws://127.0.0.1:9/v1/ws?token=${TOKEN}`);
      socket = { onmessage: null, onopen: null, onclose: null, close() {} };
      return socket;
    });

    events.connect();
    await deliver(socket, { op: "hello", v: 1, seq: 0 });
    await deliver(socket, { seq: 1, type: "job.state" });
    await deliver(socket, { seq: 2, type: "job.progress" });
    expect(seen).toEqual([]);
    expect(events.last).toBe(2);

    await deliver(socket, { seq: 4, type: "job.chunk" });
    expect(seen).toEqual(["http://127.0.0.1:9/v1/events?since=2"]);
    expect(events.last).toBe(4);
    expect(events.applied.map((frame) => frame.seq)).toEqual([1, 2, 3, 4]);

    await deliver(socket, { seq: 4, type: "job.chunk" });
    expect(seen).toEqual(["http://127.0.0.1:9/v1/events?since=2"]);
  });
});

function deliver(socket: MinimalSocket, message: unknown): Promise<void> {
  const pending = socket.onmessage?.({ data: JSON.stringify(message) });
  return Promise.resolve(pending).then(() => undefined);
}
