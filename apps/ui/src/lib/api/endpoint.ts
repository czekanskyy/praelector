// SPDX-License-Identifier: Apache-2.0
import { z } from "zod";

import type { EngineCoordinates } from "./types";

const portToken = z.object({
  port: z.number().int().min(1).max(65535),
  token: z.string().min(1),
});

const baseUrlToken = z.object({
  baseUrl: z.string().min(1),
  token: z.string().min(1),
});

const coded = z.object({
  code: z.string().min(1),
});

export class EngineRequestError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "EngineRequestError";
    this.code = code;
  }
}

/**
 * Accepts the plan's `{port, token}` and the desktop shell's `{baseUrl, token}`
 * (`EngineEndpoint` serialises `base_url`). Only loopback HTTP is usable: the
 * client always dials `127.0.0.1` itself.
 */
export function parseEngineEndpoint(raw: unknown): EngineCoordinates {
  const direct = portToken.safeParse(raw);
  if (direct.success) {
    return { port: direct.data.port, token: direct.data.token };
  }
  const viaUrl = baseUrlToken.safeParse(raw);
  if (viaUrl.success) {
    const port = loopbackPort(viaUrl.data.baseUrl);
    if (port !== null) return { port, token: viaUrl.data.token };
  }
  throw new EngineRequestError("engine.not_ready");
}

export async function loadEngineEndpoint(): Promise<EngineCoordinates> {
  const { invoke } = await import("@tauri-apps/api/core");
  return parseEngineEndpoint(await invoke("engine_endpoint"));
}

/** Stable code from a Tauri rejection or an {@link EngineRequestError}. */
export function failureCode(error: unknown): string {
  if (error instanceof EngineRequestError) return error.code;
  const direct = coded.safeParse(error);
  if (direct.success) return direct.data.code;
  const message = error instanceof Error ? error.message : error;
  if (typeof message === "string") {
    try {
      const nested = coded.safeParse(JSON.parse(message));
      if (nested.success) return nested.data.code;
    } catch {
      // Not JSON. Fall through to the generic not-ready code.
    }
  }
  return "engine.not_ready";
}

function loopbackPort(baseUrl: string): number | null {
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1") return null;
  const port = Number(url.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  return port;
}
