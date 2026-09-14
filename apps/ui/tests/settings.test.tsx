// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "../src/i18n";
import { SettingsScreen } from "../src/features/settings/SettingsScreen";

// Mock api client
vi.mock("../src/lib/api/client", () => ({
  api: {
    listLlmProfiles: vi.fn().mockResolvedValue([
      {
        id: "llm_local_ollama",
        name: "Ollama Local",
        preset: "ollama",
        kind: "openai_compatible",
        base_url: "http://127.0.0.1:11434/v1",
        model: "qwen2.5:14b-instruct",
        is_cloud: false,
        supports_json_schema: true,
        timeout_s: 120,
        max_tokens: 1024,
        api_key: { set: false },
      },
    ]),
    getTaskRouting: vi.fn().mockResolvedValue({
      classify_cheap: "llm_local_ollama",
      dialogue_hard: "llm_local_ollama",
      pronounce: "llm_local_ollama",
    }),
    testLlmProfile: vi.fn().mockResolvedValue({
      ok: true,
      latency_ms: 125.0,
      models: ["qwen2.5:14b-instruct"],
    }),
    updateTaskRouting: vi.fn().mockResolvedValue({
      classify_cheap: "llm_local_ollama",
      dialogue_hard: "llm_local_ollama",
      pronounce: "llm_local_ollama",
    }),
    createLlmProfile: vi.fn(),
    updateLlmProfile: vi.fn(),
    deleteLlmProfile: vi.fn(),
  },
}));

describe("SettingsScreen", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  it("renders LLM provider notices, profiles, and routing sections", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <SettingsScreen />
        </I18nextProvider>
      </QueryClientProvider>,
    );

    // Verify subscription warning banner is displayed (LM-06)
    expect(
      screen.getByText(/ChatGPT Plus, Claude Pro, Gemini Advanced, and Cursor subscriptions do not grant API access/i)
    ).toBeDefined();

    // Verify free tier on-ramp information is displayed (LM-06)
    expect(
      screen.getByText(/Free and low-cost API on-ramps/i)
    ).toBeDefined();

    // Verify LLM Providers header and Add Profile button (LM-01)
    expect(screen.getByText("LLM Providers")).toBeDefined();
    expect(screen.getByText("Add Provider Profile")).toBeDefined();

    // Verify Task Routing section (LM-04)
    expect(screen.getByText("Task Routing")).toBeDefined();
    expect(screen.getByText("Save Task Routing")).toBeDefined();
  });
});
