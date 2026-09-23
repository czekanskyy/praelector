// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";

import { EngineApi, type ProjectSummary } from "../src/lib/api/client";
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

  it("lists projects on the port taken from the shell base URL", async () => {
    const coords = parseEngineEndpoint({ baseUrl: "http://127.0.0.1:4312", token: TOKEN });
    const seen: string[] = [];
    const fetchImpl: typeof fetch = async (input) => {
      seen.push(String(input));
      return jsonResponse({
        projects: [],
        projects_dir: "/books",
        open_project_id: null,
      });
    };
    const api = new EngineApi(coords, fetchImpl);
    await expect(api.listProjects()).resolves.toEqual({
      projects: [],
      projects_dir: "/books",
      open_project_id: null,
    });
    expect(seen).toEqual(["http://127.0.0.1:4312/v1/projects"]);
  });

  it("parses a library row, including an unreadable project", async () => {
    const readable = summary();
    const unreadable = summary({
      id: "broken-folder",
      name: "broken-folder",
      created_at: null,
      updated_at: null,
      unreadable: true,
      path: "/books/broken-folder",
    });
    const fetchImpl: typeof fetch = async () =>
      jsonResponse({
        projects: [readable, unreadable],
        projects_dir: "/books",
        open_project_id: readable.id,
      });
    const api = new EngineApi({ port: 9, token: TOKEN }, fetchImpl);
    await expect(api.listProjects()).resolves.toEqual({
      projects: [readable, unreadable],
      projects_dir: "/books",
      open_project_id: readable.id,
    });
  });

  it("creates a project without a directory override", async () => {
    let seen: { url: string; method: string; contentType: string | null; origin: string | null; body: unknown } =
      { url: "", method: "", contentType: null, origin: null, body: null };
    const fetchImpl: typeof fetch = async (input, init) => {
      const headers = new Headers(init?.headers);
      seen = {
        url: String(input),
        method: init?.method ?? "",
        contentType: headers.get("Content-Type"),
        origin: headers.get("Origin"),
        body: JSON.parse(String(init?.body)),
      };
      return jsonResponse({
        ...summary(),
        schema_version: 1,
        db_revision: "0001_baseline",
        cloud_llm_enabled: false,
      }, 201);
    };
    const api = new EngineApi({ port: 9, token: TOKEN }, fetchImpl);
    await expect(api.createProject("Lalka")).resolves.toEqual(summary());
    expect(seen).toEqual({
      url: "http://127.0.0.1:9/v1/projects",
      method: "POST",
      contentType: "application/json",
      origin: null,
      body: { name: "Lalka", spoken_language: "pl", voice_mode: "single" },
    });
    expect(seen.body).not.toHaveProperty("dir");
  });

  it("opens a project by id and keeps an engine error code", async () => {
    const opened = summary({ is_open: true });
    let method = "";
    let contentType: string | null = "unset";
    const fetchImpl: typeof fetch = async (input, init) => {
      method = init?.method ?? "";
      contentType = new Headers(init?.headers).get("Content-Type");
      expect(String(input)).toBe(`http://127.0.0.1:9/v1/projects/${opened.id}/open`);
      expect(init?.body).toBeUndefined();
      return jsonResponse(opened);
    };
    const api = new EngineApi({ port: 9, token: TOKEN }, fetchImpl);
    await expect(api.openProject(opened.id)).resolves.toEqual(opened);
    expect(method).toBe("POST");
    expect(contentType).toBeNull();

    const rejected: typeof fetch = async () =>
      jsonResponse({ error: { code: "project.already_open", detail: {} } }, 409);
    const failing = new EngineApi({ port: 9, token: TOKEN }, rejected);
    await expect(failing.openProject(opened.id)).rejects.toMatchObject({
      code: "project.already_open",
    });
    await expect(failing.openProject("")).rejects.toMatchObject({
      code: "internal.validation_failed",
    });
  });

  it("turns a transport failure or a bad body into a stable code", async () => {
    const down: typeof fetch = async () => {
      throw new TypeError("connect");
    };
    const api = new EngineApi({ port: 9, token: TOKEN }, down);
    await expect(api.listProjects()).rejects.toMatchObject({ code: "engine.not_ready" });

    const invalid: typeof fetch = async () => jsonResponse({ projects: [] });
    const bad = new EngineApi({ port: 9, token: TOKEN }, invalid);
    await expect(bad.listProjects()).rejects.toMatchObject({
      code: "internal.validation_failed",
    });

    const emptyName: typeof fetch = async () =>
      jsonResponse({ error: { code: "internal.validation_failed" } }, 422);
    const create = new EngineApi({ port: 9, token: TOKEN }, emptyName);
    await expect(create.createProject("")).rejects.toBeInstanceOf(EngineRequestError);
    await expect(create.createProject("")).rejects.toMatchObject({
      code: "internal.validation_failed",
    });
  });
});

function summary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    name: "Lalka",
    created_at: "2026-09-23T12:00:00+00:00",
    updated_at: "2026-09-23T12:30:00+00:00",
    voice_mode: "single",
    backend_id: null,
    spoken_language: "pl",
    current_revision: 0,
    path: "/books/prj_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    is_open: false,
    unreadable: false,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}
