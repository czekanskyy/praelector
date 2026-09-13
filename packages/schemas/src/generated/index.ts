// SPDX-License-Identifier: Apache-2.0
/**
 * Generated TypeScript contracts from Praelector domain models.
 */

export interface HealthResponse {
  status: string;
  uptime_s: number;
  project_open: boolean;
  active_job_id: string | null;
}

export interface VersionResponse {
  app: string;
  engine: string;
  schema: number;
  python: string;
  platform: string;
}

export interface ErrorPayload {
  code: string;
  detail: Record<string, unknown>;
  retryable: boolean;
  trace_id: string;
}

export interface ErrorEnvelope {
  error: ErrorPayload;
}
