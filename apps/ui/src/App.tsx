// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { apiFetch, setEngineEndpoint } from "./lib/api/client";
import { NAV_ITEMS, NavTab } from "./routes";
import { LibraryScreen } from "./features/library/LibraryScreen";
import { EditorScreen } from "./features/editor/EditorScreen";
import { SettingsScreen } from "./features/settings/SettingsScreen";
import type { HealthResponse, VersionResponse } from "@praelector/schemas";
import { AlertTriangle, Globe, RefreshCw } from "lucide-react";

interface EngineEndpointResult {
  base_url: string;
  token: string;
  version: string;
  schema: number;
}

export function App() {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<NavTab>("library");
  const [isReady, setIsReady] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);

  useEffect(() => {
    async function initEndpoint() {
      try {
        // Try invoking Tauri command for engine endpoint
        const endpoint = await invoke<EngineEndpointResult>("engine_endpoint");
        setEngineEndpoint(endpoint.base_url, endpoint.token);
        setIsReady(true);
      } catch {
        // Fallback for browser-only dev server
        setEngineEndpoint("http://127.0.0.1:54321/v1", "");
        setIsReady(true);
      }
    }

    initEndpoint().catch((err) => {
      setInitError(String(err));
    });
  }, []);

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    enabled: isReady,
    refetchInterval: 5000,
  });

  const versionQuery = useQuery({
    queryKey: ["version"],
    queryFn: () => apiFetch<VersionResponse>("/version"),
    enabled: isReady,
  });

  const toggleLanguage = () => {
    const nextLang = i18n.language === "pl" ? "en" : "pl";
    i18n.changeLanguage(nextLang);
  };

  if (initError) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background p-8 text-foreground">
        <AlertTriangle className="mb-4 h-12 w-12 text-destructive" />
        <h1 className="mb-2 text-xl font-bold">{t("common:status.error")}</h1>
        <p className="mb-4 text-sm text-muted-foreground">{initError}</p>
        <button
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <RefreshCw className="h-4 w-4" />
          {t("common:actions.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-border bg-card">
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-primary text-primary-foreground font-bold">
            P
          </div>
          <div>
            <h1 className="text-base font-semibold leading-none">
              {t("common:appName")}
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              v{versionQuery.data?.app || "0.1.0"}
            </p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-4">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {t(item.labelKey)}
              </button>
            );
          })}
        </nav>

        {/* Footer controls: language switch & engine status */}
        <div className="border-t border-border p-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  healthQuery.isSuccess ? "bg-green-500" : "bg-amber-500"
                }`}
              />
              {healthQuery.isSuccess
                ? t("common:status.ready")
                : t("common:status.connecting")}
            </span>
            <button
              onClick={toggleLanguage}
              className="flex items-center gap-1 rounded px-2 py-1 hover:bg-muted hover:text-foreground font-medium uppercase"
            >
              <Globe className="h-3 w-3" />
              {i18n.language}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto p-8">
        <div className={`mx-auto space-y-6 ${activeTab === "editor" ? "max-w-7xl" : "max-w-4xl"}`}>
          <header className="border-b border-border pb-4">
            <h2 className="text-2xl font-bold tracking-tight">
              {t(NAV_ITEMS.find((n) => n.id === activeTab)?.labelKey || "common:appName")}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("common:tagline")}
            </p>
          </header>

          {activeTab === "library" && (
            <LibraryScreen onNavigateToEditor={() => setActiveTab("editor")} />
          )}

          {activeTab === "editor" && <EditorScreen />}

          {activeTab === "settings" && <SettingsScreen />}

          {activeTab !== "library" && activeTab !== "editor" && activeTab !== "settings" && (
            <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
              <p className="text-sm">
                Module for {activeTab} will be initialized in upcoming milestone PRs.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
