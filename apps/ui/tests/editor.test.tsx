// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "../src/i18n";
import { EditorScreen } from "../src/features/editor/EditorScreen";
import { IngestModal } from "../src/features/ingest/IngestModal";
import { useProjectStore } from "../src/stores/projectStore";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

describe("EditorScreen and IngestModal", () => {
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

  it("renders empty state when no active project is open", () => {
    useProjectStore.setState({ activeProjectId: null });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <EditorScreen />
        </I18nextProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Brak otwartego projektu")).toBeDefined();
  });

  it("renders IngestModal dropzone and file path input when open", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <IngestModal
            projectId="prj_test123"
            isOpen={true}
            onClose={() => {}}
          />
        </I18nextProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Import Ebook")).toBeDefined();
    expect(screen.getByText("Select File")).toBeDefined();
    expect(screen.getByPlaceholderText("C:\\e-books\\ksiazka.epub")).toBeDefined();
  });
});
