// SPDX-License-Identifier: Apache-2.0
import { z } from "zod";

import { EngineRequestError } from "./endpoint";
import type { EngineCoordinates, SeqFrame } from "./types";

const replaySchema = z.array(
  z.object({
    seq: z.number().int().positive(),
    type: z.string().min(1),
    payload: z.unknown().optional(),
  }),
);

const errorEnvelope = z.object({
  error: z.object({
    code: z.string().min(1),
  }),
});

/**
 * The only `fetch` in the UI. Calls `http://127.0.0.1:{port}` with
 * `Authorization: Bearer`. Origin is left unset: a browser sets it itself, and
 * an extra Origin is rejected unless it is on the engine allow-list (D-10).
 */
export class EngineApi {
  constructor(
    private readonly endpoint: EngineCoordinates,
    private readonly fetchImpl: typeof fetch = globalThis.fetch,
  ) {}

  eventsSince(since: number): Promise<SeqFrame[]> {
    if (!Number.isInteger(since) || since < 0) {
      return Promise.reject(new EngineRequestError("internal.validation_failed"));
    }
    return this.getJson(`/v1/events?since=${since}`, replaySchema);
  }

  private async getJson<T>(path: string, schema: { safeParse(data: unknown): ParseResult<T> }): Promise<T> {
    const response = await this.fetchImpl(this.url(path), {
      method: "GET",
      headers: authorizedHeaders(this.endpoint.token),
      cache: "no-store",
      credentials: "omit",
    });
    const body = await readBody(response);
    if (!response.ok) throw new EngineRequestError(codeFromBody(body));
    const parsed = schema.safeParse(body);
    if (!parsed.success || parsed.data === undefined) {
      throw new EngineRequestError("internal.validation_failed");
    }
    return parsed.data;
  }

  private url(path: string): string {
    if (!path.startsWith("/")) {
      throw new EngineRequestError("internal.validation_failed");
    }
    return `http://127.0.0.1:${this.endpoint.port}${path}`;
  }
}

interface ParseResult<T> {
  success: boolean;
  data?: T;
}

function authorizedHeaders(token: string): Headers {
  const headers = new Headers();
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function codeFromBody(body: unknown): string {
  const parsed = errorEnvelope.safeParse(body);
  return parsed.success ? parsed.data.error.code : "internal.error";
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
