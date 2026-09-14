// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Key, Info } from "lucide-react";
import type { LlmProfile, LlmProfileCreate, LlmProfilePatch } from "@praelector/schemas";
import { api } from "../../lib/api/client";
import { PROVIDER_PRESETS, ProviderPreset } from "./presets";

interface LlmProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profileToEdit?: LlmProfile | null;
}

export function LlmProfileModal({
  isOpen,
  onClose,
  profileToEdit,
}: LlmProfileModalProps): React.ReactElement | null {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const isEditing = Boolean(profileToEdit);

  const [preset, setPreset] = useState<string>("ollama");
  const [name, setName] = useState<string>("");
  const [kind, setKind] = useState<string>("ollama");
  const [baseUrl, setBaseUrl] = useState<string>("http://127.0.0.1:11434/v1");
  const [model, setModel] = useState<string>("qwen2.5:14b-instruct");
  const [apiKey, setApiKey] = useState<string>("");
  const [timeoutS, setTimeoutS] = useState<number>(120);
  const [maxTokens, setMaxTokens] = useState<number>(1024);
  const [isCloud, setIsCloud] = useState<boolean>(false);
  const [supportsJsonSchema, setSupportsJsonSchema] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (profileToEdit) {
      setName(profileToEdit.name || profileToEdit.preset || "LLM Profile");
      setPreset(profileToEdit.preset || "ollama");
      setKind(profileToEdit.kind || "openai_compatible");
      setBaseUrl(profileToEdit.base_url || "");
      setModel(profileToEdit.model || "");
      setTimeoutS(profileToEdit.timeout_s ?? 120);
      setMaxTokens(profileToEdit.max_tokens ?? 1024);
      setIsCloud(Boolean(profileToEdit.is_cloud));
      setSupportsJsonSchema(Boolean(profileToEdit.supports_json_schema));
      setApiKey("");
      setErrorMsg(null);
    } else {
      // Default to first preset (Ollama)
      applyPreset(PROVIDER_PRESETS[0]);
      setApiKey("");
      setErrorMsg(null);
    }
  }, [profileToEdit, isOpen]);

  const applyPreset = (p: ProviderPreset) => {
    setPreset(p.preset);
    setKind(p.kind);
    setName(p.name);
    setBaseUrl(p.baseUrl);
    setModel(p.defaultModel);
    setIsCloud(p.isCloud);
    setSupportsJsonSchema(p.supportsJsonSchema);
  };

  const handlePresetChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selected = PROVIDER_PRESETS.find((p) => p.preset === e.target.value);
    if (selected) {
      applyPreset(selected);
    }
  };

  const createMutation = useMutation({
    mutationFn: (payload: LlmProfileCreate) => api.createLlmProfile(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-profiles"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      onClose();
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: LlmProfilePatch }) =>
      api.updateLlmProfile(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-profiles"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      onClose();
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
    },
  });

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (isEditing && profileToEdit) {
      const patch: LlmProfilePatch = {
        name,
        kind,
        preset,
        base_url: baseUrl,
        model,
        timeout_s: timeoutS,
        max_tokens: maxTokens,
        is_cloud: isCloud,
        supports_json_schema: supportsJsonSchema,
      };
      if (apiKey.trim()) {
        patch.api_key = apiKey.trim();
      }
      updateMutation.mutate({ id: profileToEdit.id, patch });
    } else {
      const payload: LlmProfileCreate = {
        name,
        kind,
        preset,
        base_url: baseUrl,
        model,
        timeout_s: timeoutS,
        max_tokens: maxTokens,
        is_cloud: isCloud,
        supports_json_schema: supportsJsonSchema,
        api_key: apiKey.trim() || undefined,
      };
      createMutation.mutate(payload);
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-border bg-card shadow-2xl text-foreground">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-lg font-semibold">
            {isEditing ? t("settings:editProfile") : t("settings:addProfile")}
          </h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content / Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {errorMsg && (
            <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive font-medium">
              {errorMsg}
            </div>
          )}

          {!isEditing && (
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {t("settings:providerPreset")}
              </label>
              <select
                value={preset}
                onChange={handlePresetChange}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {PROVIDER_PRESETS.map((p) => (
                  <option key={p.id} value={p.preset}>
                    {p.name} {p.isCloud ? "(Cloud)" : "(Local)"}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              {t("settings:profileName")}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              {t("settings:baseUrl")}
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              {t("settings:modelName")}
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("settings:apiKey")}
              </label>
              {isEditing && profileToEdit?.api_key?.set && (
                <span className="text-xs text-green-500 font-medium flex items-center gap-1">
                  <Key className="h-3 w-3" /> {t("settings:apiKeyConfigured")}
                </span>
              )}
            </div>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                isEditing && profileToEdit?.api_key?.set
                  ? t("settings:apiKeyPlaceholderEdit")
                  : "sk-..."
              }
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
              <Info className="h-3.5 w-3.5" />
              {t("settings:apiKeyHelp")}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {t("settings:timeoutSeconds")}
              </label>
              <input
                type="number"
                value={timeoutS}
                onChange={(e) => setTimeoutS(Number(e.target.value))}
                min={5}
                max={600}
                required
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {t("settings:maxTokens")}
              </label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                min={64}
                max={16384}
                required
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={isCloud}
                onChange={(e) => setIsCloud(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
              <span className="text-sm font-medium">{t("settings:isCloud")}</span>
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={supportsJsonSchema}
                onChange={(e) => setSupportsJsonSchema(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
              <span className="text-sm font-medium">
                {t("settings:supportsJsonSchema")}
              </span>
            </label>
          </div>

          {/* Footer actions */}
          <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
            >
              {t("settings:cancel")}
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isPending ? "..." : t("settings:save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
