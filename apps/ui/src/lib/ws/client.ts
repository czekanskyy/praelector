// SPDX-License-Identifier: Apache-2.0
import { z } from "zod";

import type { EngineCoordinates, SeqFrame } from "../api/types";
import { gapSince } from "./gap";

const helloSchema = z.object({
  op: z.literal("hello"),
  seq: z.number().int().nonnegative(),
});

const pongSchema = z.object({
  op: z.literal("pong"),
});

const overflowSchema = z.object({
  op: z.literal("overflow"),
});

const eventSchema = z.object({
  seq: z.number().int().positive(),
  type: z.string().min(1),
  payload: z.unknown().optional(),
});

export interface EventReplay {
  eventsSince(since: number): Promise<SeqFrame[]>;
}

export interface MinimalSocket {
  onmessage: ((event: { data: unknown }) => unknown) | null;
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  close(): void;
}

type Incoming =
  | { kind: "hello"; seq: number }
  | { kind: "pong" }
  | { kind: "overflow" }
  | { kind: "event"; frame: SeqFrame };

/**
 * Tracks `seq` on `ws://127.0.0.1:{port}/v1/ws?token=`.
 *
 * The WebView's `WebSocket` constructor cannot set headers, so the engine
 * accepts the bearer token as a query parameter. A hole does not move the
 * cursor; the missing frames are loaded with `GET /v1/events?since=<last>`
 * through the API client, which is the only module allowed to call `fetch`.
 */
export class EngineEvents {
  last = 0;
  readonly applied: SeqFrame[] = [];

  private socket: MinimalSocket | null = null;
  private seenHello = false;
  private stopped = false;

  constructor(
    private readonly endpoint: EngineCoordinates,
    private readonly replay: EventReplay,
    private readonly openSocket: (url: string) => MinimalSocket = browserSocket,
  ) {}

  connect(): void {
    this.stopped = false;
    const socket = this.openSocket(wsUrl(this.endpoint));
    this.socket = socket;
    socket.onmessage = (event) => this.consume(event.data);
  }

  close(): void {
    this.stopped = true;
    this.socket?.close();
    this.socket = null;
  }

  private async consume(data: unknown): Promise<void> {
    const incoming = parseIncoming(data);
    if (!incoming || this.stopped) return;
    if (incoming.kind === "hello") {
      if (!this.seenHello) {
        this.last = incoming.seq;
        this.seenHello = true;
        return;
      }
      if (incoming.seq > this.last) await this.fill(this.last);
      return;
    }
    if (incoming.kind === "pong") return;
    if (incoming.kind === "overflow") {
      await this.fill(this.last);
      return;
    }
    const since = gapSince(this.last, incoming.frame.seq);
    if (since !== null) await this.fill(since);
    this.take(incoming.frame);
  }

  private async fill(since: number): Promise<void> {
    let frames: SeqFrame[];
    try {
      frames = await this.replay.eventsSince(since);
    } catch {
      // Leave `last` where it is so the next frame asks for the same hole.
      return;
    }
    if (this.stopped) return;
    for (const frame of [...frames].sort((left, right) => left.seq - right.seq)) {
      this.take(frame);
    }
  }

  private take(frame: SeqFrame): void {
    if (frame.seq !== this.last + 1) return;
    this.last = frame.seq;
    this.applied.push(frame);
  }
}

export function wsUrl(endpoint: EngineCoordinates): string {
  const token = encodeURIComponent(endpoint.token);
  return `ws://127.0.0.1:${endpoint.port}/v1/ws?token=${token}`;
}

function parseIncoming(data: unknown): Incoming | null {
  if (typeof data !== "string") return null;
  let json: unknown;
  try {
    json = JSON.parse(data);
  } catch {
    return null;
  }
  const hello = helloSchema.safeParse(json);
  if (hello.success) return { kind: "hello", seq: hello.data.seq };
  if (pongSchema.safeParse(json).success) return { kind: "pong" };
  if (overflowSchema.safeParse(json).success) return { kind: "overflow" };
  const event = eventSchema.safeParse(json);
  if (!event.success) return null;
  return {
    kind: "event",
    frame: {
      seq: event.data.seq,
      type: event.data.type,
      payload: event.data.payload,
    },
  };
}

function browserSocket(url: string): MinimalSocket {
  const socket = new WebSocket(url);
  const bridge: MinimalSocket = {
    onmessage: null,
    onopen: null,
    onclose: null,
    close() {
      socket.close();
    },
  };
  socket.addEventListener("message", (event) => {
    void bridge.onmessage?.({ data: event.data });
  });
  socket.addEventListener("open", () => {
    bridge.onopen?.();
  });
  socket.addEventListener("close", () => {
    bridge.onclose?.();
  });
  return bridge;
}
