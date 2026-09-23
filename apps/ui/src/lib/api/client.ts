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

const projectSummarySchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  created_at: z.string().min(1).nullable(),
  updated_at: z.string().min(1).nullable(),
  voice_mode: z.enum(["single", "narrator_dialogue", "narrator_male_female"]),
  backend_id: z.string().nullable(),
  spoken_language: z.string().min(1),
  current_revision: z.number().int().nonnegative(),
  path: z.string().min(1),
  is_open: z.boolean(),
  unreadable: z.boolean(),
});

const projectListSchema = z.object({
  projects: z.array(projectSummarySchema),
  projects_dir: z.string().min(1),
  open_project_id: z.string().min(1).nullable(),
});

export type ProjectSummary = z.infer<typeof projectSummarySchema>;
export type ProjectListResponse = z.infer<typeof projectListSchema>;

/**
 * The only `fetch` in the UI. Calls `http://127.0.0.1:{port}` with
 * `Authorization: Bearer`. Origin is left unset: a browser sets it itself, and
 * an extra Origin is rejected unless it is on the engine allow-list (D-10).
 *
 * Callers pass `EngineCoordinates`. `parseEngineEndpoint` is what accepts the
 * desktop command's `{ baseUrl, token }` shape and turns it into a loopback port.
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
    return this.requestJson(`/v1/events?since=${since}`, replaySchema);
  }

  listProjects(): Promise<ProjectListResponse> {
    return this.requestJson("/v1/projects", projectListSchema);
  }

  /**
   * `dir` is omitted on purpose: the engine chooses the folder under `projects_dir`.
   * An empty name comes back as `internal.validation_failed`.
   */
  createProject(name: string): Promise<ProjectSummary> {
    return this.requestJson("/v1/projects", projectSummarySchema, {
      method: "POST",
      json: {
        name,
        spoken_language: "pl",
        voice_mode: "single",
      },
    });
  }

  openProject(id: string): Promise<ProjectSummary> {
    if (id.length === 0) {
      return Promise.reject(new EngineRequestError("internal.validation_failed"));
    }
    return this.requestJson(`/v1/projects/${encodeURIComponent(id)}/open`, projectSummarySchema, {
      method: "POST",
    });
  }

  private async requestJson<T>(
    path: string,
    schema: { safeParse(data: unknown): ParseResult<T> },
    init?: { method?: "GET" | "POST"; json?: unknown },
  ): Promise<T> {
    const headers = authorizedHeaders(this.endpoint.token);
    let body: string | undefined;
    if (init?.json !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(init.json);
    }
    let response: Response;
    try {
      response = await this.fetchImpl(this.url(path), {
        method: init?.method ?? "GET",
        headers,
        body,
        cache: "no-store",
        credentials: "omit",
      });
    } catch {
      throw new EngineRequestError("engine.not_ready");
    }
    const payload = await readBody(response);
    if (!response.ok) throw new EngineRequestError(codeFromBody(payload));
    const parsed = schema.safeParse(payload);
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
