// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Edit2,
  Key,
  Plus,
  Radio,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { LlmProfile, LlmTestResponse, TaskRouting } from "@praelector/schemas";
import { api } from "../../lib/api/client";
import { LlmProfileModal } from "./LlmProfileModal";

export function SettingsScreen(): React.ReactElement {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [profileToEdit, setProfileToEdit] = useState<LlmProfile | null>(null);
  const [testResults, setTestResults] = useState<Record<string, LlmTestResponse | null>>({});
  const [testingIds, setTestingIds] = useState<Record<string, boolean>>({});
  const [routingSuccess, setRoutingSuccess] = useState(false);

  // Queries
  const profilesQuery = useQuery({
    queryKey: ["llm-profiles"],
    queryFn: api.listLlmProfiles,
  });

  const routingQuery = useQuery({
    queryKey: ["task-routing"],
    queryFn: api.getTaskRouting,
  });

  // Task routing state
  const [taskRouting, setTaskRouting] = useState<TaskRouting>({
    classify_cheap: "llm_local_ollama",
    dialogue_hard: "llm_local_ollama",
    pronounce: "llm_local_ollama",
  });

  React.useEffect(() => {
    if (routingQuery.data) {
      setTaskRouting(routingQuery.data);
    }
  }, [routingQuery.data]);

  // Mutations
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteLlmProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-profiles"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const routingMutation = useMutation({
    mutationFn: (data: TaskRouting) => api.updateTaskRouting(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-routing"] });
      setRoutingSuccess(true);
      setTimeout(() => setRoutingSuccess(false), 3000);
    },
  });

  const handleTestConnection = async (profileId: string) => {
    setTestingIds((prev) => ({ ...prev, [profileId]: true }));
    try {
      const res = await api.testLlmProfile(profileId);
      setTestResults((prev) => ({ ...prev, [profileId]: res }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [profileId]: {
          ok: false,
          error: String(err),
        },
      }));
    } finally {
      setTestingIds((prev) => ({ ...prev, [profileId]: false }));
    }
  };

  const handleOpenAdd = () => {
    setProfileToEdit(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (profile: LlmProfile) => {
    setProfileToEdit(profile);
    setIsModalOpen(true);
  };

  const handleDelete = (profile: LlmProfile) => {
    if (window.confirm(`Delete profile "${profile.name || profile.id}"?`)) {
      deleteMutation.mutate(profile.id);
    }
  };

  const profiles = profilesQuery.data || [];

  return (
    <div className="space-y-8">
      {/* On-Ramp Notice (LM-06) */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-card-foreground">
        <div className="flex gap-3">
          <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-amber-600 dark:text-amber-400">
              {t("settings:llmSubscriptionNotice")}
            </p>
            <p className="text-muted-foreground">
              {t("settings:freeTierOnRamps")}
            </p>
          </div>
        </div>
      </div>

      {/* LLM Profiles Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              {t("settings:llmProviders")}
            </h3>
            <p className="text-sm text-muted-foreground">
              {t("settings:profilesSubtitle")}
            </p>
          </div>
          <button
            onClick={handleOpenAdd}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            <Plus className="h-4 w-4" />
            {t("settings:addProfile")}
          </button>
        </div>

        {/* Profiles Grid */}
        <div className="grid gap-4 md:grid-cols-2">
          {profiles.map((p) => {
            const testResult = testResults[p.id];
            const isTesting = testingIds[p.id];

            return (
              <div
                key={p.id}
                className="flex flex-col justify-between rounded-xl border border-border bg-card p-5 shadow-sm transition-all hover:border-border/80"
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="font-semibold text-base">{p.name || p.preset || p.id}</h4>
                      <p className="text-xs font-mono text-muted-foreground">{p.model}</p>
                    </div>
                    <div className="flex gap-1.5 flex-wrap justify-end">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.is_cloud
                            ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                            : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                        }`}
                      >
                        {p.is_cloud ? t("settings:cloudService") : t("settings:localRunner")}
                      </span>
                      {p.supports_json_schema && (
                        <span className="inline-flex items-center rounded-full bg-purple-500/10 px-2 py-0.5 text-xs font-medium text-purple-600 dark:text-purple-400">
                          {t("settings:jsonSchemaSupported")}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground space-y-1">
                    <p className="truncate font-mono">
                      <span className="text-foreground/70 font-sans">Base URL:</span> {p.base_url}
                    </p>
                    <div className="flex items-center gap-3">
                      <span>Timeout: {p.timeout_s}s</span>
                      <span>•</span>
                      <span>Max tokens: {p.max_tokens}</span>
                      {p.api_key && (
                        <>
                          <span>•</span>
                          <span className="flex items-center gap-1 text-foreground/80">
                            <Key className="h-3 w-3" />
                            {p.api_key.set
                              ? t("settings:apiKeyConfigured")
                              : t("settings:apiKeyMissing")}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Test connection output */}
                  {testResult && (
                    <div
                      className={`rounded-lg p-2.5 text-xs flex items-center gap-2 ${
                        testResult.ok
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium"
                          : "bg-destructive/10 text-destructive font-medium"
                      }`}
                    >
                      {testResult.ok ? (
                        <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
                      ) : (
                        <AlertCircle className="h-4 w-4 flex-shrink-0" />
                      )}
                      <span>
                        {testResult.ok
                          ? t("settings:connectionOk", { latency: testResult.latency_ms })
                          : testResult.error || t("settings:connectionFailed")}
                      </span>
                    </div>
                  )}
                </div>

                {/* Card Actions */}
                <div className="mt-5 flex items-center justify-between border-t border-border pt-3">
                  <button
                    onClick={() => handleTestConnection(p.id)}
                    disabled={isTesting}
                    className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-border hover:bg-muted text-foreground transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isTesting ? "animate-spin" : ""}`} />
                    {isTesting ? t("settings:testingConnection") : t("settings:testConnection")}
                  </button>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleOpenEdit(p)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                      title={t("settings:editProfile")}
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(p)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/15 hover:text-destructive transition-colors"
                      title={t("settings:deleteProfile")}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Task Routing Section (LM-04) */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-sm space-y-6">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Radio className="h-5 w-5 text-primary" />
            {t("settings:taskRoutingTitle")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {t("settings:taskRoutingSubtitle")}
          </p>
        </div>

        <div className="space-y-4 divide-y divide-border">
          {/* classify_cheap */}
          <div className="pt-4 first:pt-0 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold">{t("settings:classifyCheapLabel")}</h4>
              <p className="text-xs text-muted-foreground">{t("settings:classifyCheapDesc")}</p>
            </div>
            <select
              value={taskRouting.classify_cheap || ""}
              onChange={(e) =>
                setTaskRouting((prev) => ({ ...prev, classify_cheap: e.target.value }))
              }
              className="w-full md:w-64 rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.preset} ({p.is_cloud ? "Cloud" : "Local"})
                </option>
              ))}
            </select>
          </div>

          {/* dialogue_hard */}
          <div className="pt-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold">{t("settings:dialogueHardLabel")}</h4>
              <p className="text-xs text-muted-foreground">{t("settings:dialogueHardDesc")}</p>
            </div>
            <select
              value={taskRouting.dialogue_hard || ""}
              onChange={(e) =>
                setTaskRouting((prev) => ({ ...prev, dialogue_hard: e.target.value }))
              }
              className="w-full md:w-64 rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.preset} ({p.is_cloud ? "Cloud" : "Local"})
                </option>
              ))}
            </select>
          </div>

          {/* pronounce */}
          <div className="pt-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold">{t("settings:pronounceLabel")}</h4>
              <p className="text-xs text-muted-foreground">{t("settings:pronounceDesc")}</p>
            </div>
            <select
              value={taskRouting.pronounce || ""}
              onChange={(e) =>
                setTaskRouting((prev) => ({ ...prev, pronounce: e.target.value }))
              }
              className="w-full md:w-64 rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.preset} ({p.is_cloud ? "Cloud" : "Local"})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-border">
          {routingSuccess ? (
            <span className="text-xs text-emerald-500 font-medium flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4" /> {t("settings:routingSaved")}
            </span>
          ) : (
            <span />
          )}
          <button
            onClick={() => routingMutation.mutate(taskRouting)}
            disabled={routingMutation.isPending}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            {routingMutation.isPending ? "..." : t("settings:saveRouting")}
          </button>
        </div>
      </div>

      {/* Modal */}
      <LlmProfileModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        profileToEdit={profileToEdit}
      />
    </div>
  );
}
