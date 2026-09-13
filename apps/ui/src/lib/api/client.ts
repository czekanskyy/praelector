// SPDX-License-Identifier: Apache-2.0
import type {
  AppSettings,
  CapabilitiesResponse,
  ErrorEnvelope,
  HealthResponse,
  ProjectCreate,
  ProjectOpenResponse,
  ProjectResponse,
  ProjectStats,
  ProjectSummary,
  ProjectUpdate,
  SettingsUpdate,
  VersionResponse,
} from "@praelector/schemas";

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    public readonly detail: Record<string, unknown>,
    public readonly retryable: boolean,
    public readonly traceId: string,
  ) {
    super(`API Error [${code}]: ${JSON.stringify(detail)}`);
    this.name = "ApiError";
  }
}

interface EngineEndpoint {
  baseUrl: string;
  token: string;
}

let currentEndpoint: EngineEndpoint = {
  baseUrl: "http://127.0.0.1:54321/v1",
  token: "",
};

export function setEngineEndpoint(baseUrl: string, token: string): void {
  currentEndpoint = { baseUrl, token };
}

export function getEngineEndpoint(): EngineEndpoint {
  return currentEndpoint;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const { baseUrl, token } = currentEndpoint;
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;

  const headers = new Headers(init.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let errorEnvelope: ErrorEnvelope | null = null;
    try {
      errorEnvelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // Non-JSON response
    }

    if (errorEnvelope?.error) {
      throw new ApiError(
        errorEnvelope.error.code,
        response.status,
        errorEnvelope.error.detail,
        errorEnvelope.error.retryable,
        errorEnvelope.error.trace_id,
      );
    }

    throw new ApiError(
      "internal.http_error",
      response.status,
      { statusText: response.statusText },
      response.status >= 500,
      "",
    );
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return (await response.json()) as T;
}

export const api = {
  getHealth: () => apiFetch<HealthResponse>("/health"),
  getVersion: () => apiFetch<VersionResponse>("/version"),
  getCapabilities: () => apiFetch<CapabilitiesResponse>("/capabilities"),
  getSettings: () => apiFetch<AppSettings>("/settings"),
  updateSettings: (data: SettingsUpdate) =>
    apiFetch<AppSettings>("/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  listProjects: () => apiFetch<ProjectSummary[]>("/projects"),
  createProject: (data: ProjectCreate) =>
    apiFetch<ProjectResponse>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (pid: string) => apiFetch<ProjectResponse>(`/projects/${pid}`),
  updateProject: (pid: string, data: ProjectUpdate) =>
    apiFetch<ProjectResponse>(`/projects/${pid}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  openProject: (pid: string) =>
    apiFetch<ProjectOpenResponse>(`/projects/${pid}/open`, {
      method: "POST",
    }),
  closeProject: (pid: string) =>
    apiFetch<{ status: string }>(`/projects/${pid}/close`, {
      method: "POST",
    }),
  deleteProject: (pid: string, deleteFiles = false) =>
    apiFetch<{ status: string }>(`/projects/${pid}?delete_files=${deleteFiles}`, {
      method: "DELETE",
    }),
  getProjectStats: (pid: string) =>
    apiFetch<ProjectStats>(`/projects/${pid}/stats`),
};
