// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "../src/i18n";
import { LibraryScreen } from "../src/features/library/LibraryScreen";

// Mock Tauri invoke
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

describe("LibraryScreen", () => {
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

  it("renders library view with capabilities and new project action", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <LibraryScreen />
        </I18nextProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Recent Projects")).toBeDefined();
    expect(screen.getAllByText("New Project").length).toBeGreaterThan(0);
    expect(screen.getByText("FFmpeg Muxer")).toBeDefined();
  });
});
