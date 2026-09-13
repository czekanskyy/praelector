// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookPlus,
  CheckCircle2,
  FileText,
  Folder,
  HardDrive,
  Key,
  Layers,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { VoiceMode } from "@praelector/schemas";
import { api } from "../../lib/api/client";
import { IngestModal } from "../ingest/IngestModal";
import { useProjectStore } from "../../stores/projectStore";

interface LibraryScreenProps {
  onNavigateToEditor?: (projectId: string) => void;
}

export function LibraryScreen({ onNavigateToEditor }: LibraryScreenProps): React.ReactElement {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { setActiveProjectId } = useProjectStore();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [ingestProjectId, setIngestProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("narrator_male_female");
  const [language, setLanguage] = useState("pl");

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
  });

  const capabilitiesQuery = useQuery({
    queryKey: ["capabilities"],
    queryFn: api.getCapabilities,
  });

  const createMutation = useMutation({
    mutationFn: api.createProject,
    onSuccess: (newProject) => {
      setIsCreateOpen(false);
      setProjectName("");
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      // Automatically open the new project
      openMutation.mutate(newProject.id);
    },
  });

  const openMutation = useMutation({
    mutationFn: api.openProject,
    onSuccess: (res) => {
      setActiveProjectId(res.project.id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });

  const closeMutation = useMutation({
    mutationFn: api.closeProject,
    onSuccess: () => {
      setActiveProjectId(null);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteProject(id, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectName.trim()) return;
    createMutation.mutate({
      name: projectName.trim(),
      voice_mode: voiceMode,
      spoken_language: language,
    });
  };

  const caps = capabilitiesQuery.data;
  const projects = projectsQuery.data || [];

  return (
    <div className="space-y-6">
      {/* Capabilities and System Status Header */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <HardDrive className="h-5 w-5 text-primary" />
          <div className="text-sm">
            <p className="font-medium">{t("library:ffmpeg")}</p>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              {caps?.ffmpeg?.installed ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 inline" />
                  {t("library:detected")}
                </>
              ) : (
                <>
                  <XCircle className="h-3.5 w-3.5 text-amber-500 inline" />
                  {t("library:missing")}
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <Layers className="h-5 w-5 text-primary" />
          <div className="text-sm">
            <p className="font-medium">{t("library:calibre")}</p>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              {caps?.calibre?.installed ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 inline" />
                  {t("library:detected")}
                </>
              ) : (
                <>
                  <span className="text-muted-foreground">{t("library:optional")}</span>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <Key className="h-5 w-5 text-primary" />
          <div className="text-sm">
            <p className="font-medium">{t("library:keyring")}</p>
            <p className="text-xs text-muted-foreground">
              {caps?.keyring?.available
                ? t("library:systemKeyring")
                : t("library:encryptedFallback")}
            </p>
          </div>
        </div>
      </div>

      {/* Projects Controls Bar */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold tracking-tight">
          {t("library:recentProjects")}
        </h3>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <BookPlus className="h-4 w-4" />
          {t("library:newProject")}
        </button>
      </div>

      {/* Projects List */}
      {projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-12 text-center">
          <Folder className="mx-auto h-12 w-12 text-muted-foreground/50" />
          <h4 className="mt-4 text-base font-semibold">{t("library:noProjects")}</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("library:emptyStateDescription")}
          </p>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <BookPlus className="h-4 w-4" />
            {t("library:newProject")}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {projects.map((project) => (
            <div
              key={project.id}
              className={`flex flex-col justify-between rounded-lg border p-5 transition-shadow hover:shadow-md ${
                project.is_open
                  ? "border-primary/50 bg-primary/5"
                  : "border-border bg-card"
              }`}
            >
              <div>
                <div className="flex items-start justify-between">
                  <h4 className="text-base font-bold tracking-tight text-foreground">
                    {project.name}
                  </h4>
                  {project.is_open && (
                    <span className="rounded-full bg-primary/20 px-2.5 py-0.5 text-xs font-semibold text-primary">
                      {t("library:active")}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {project.path}
                </p>
                <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                  <span>
                    {t("library:voiceMode")}:{" "}
                    <strong>{project.voice_mode}</strong>
                  </span>
                  <span>
                    {t("library:revision")}:{" "}
                    <strong>{project.current_revision}</strong>
                  </span>
                </div>
              </div>

              <div className="mt-5 flex items-center justify-between border-t border-border/50 pt-3">
                <span className="text-xs text-muted-foreground">
                  {t("library:updated")}:{" "}
                  {new Date(project.updated_at).toLocaleDateString()}
                </span>
                <div className="flex items-center gap-2">
                  {project.is_open ? (
                    <>
                      <button
                        onClick={() => setIngestProjectId(project.id)}
                        className="inline-flex items-center gap-1 rounded bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground hover:bg-secondary/80"
                        title="Importuj książkę do projektu"
                      >
                        <UploadCloud className="h-3.5 w-3.5" />
                        Importuj
                      </button>
                      <button
                        onClick={() => {
                          setActiveProjectId(project.id);
                          onNavigateToEditor?.(project.id);
                        }}
                        className="inline-flex items-center gap-1 rounded bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                        title="Otwórz w edytorze"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        Edytor
                      </button>
                      <button
                        onClick={() => closeMutation.mutate(project.id)}
                        disabled={closeMutation.isPending}
                        className="rounded px-2.5 py-1 text-xs font-medium border border-border hover:bg-muted"
                      >
                        {t("library:close")}
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => openMutation.mutate(project.id)}
                      disabled={openMutation.isPending}
                      className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      {t("library:openProject")}
                    </button>
                  )}
                  <button
                    onClick={() => deleteMutation.mutate(project.id)}
                    disabled={deleteMutation.isPending}
                    className="rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    title={t("library:delete")}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* New Project Dialog */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
            <h3 className="text-lg font-semibold tracking-tight">
              {t("library:createDialogTitle")}
            </h3>
            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-muted-foreground">
                  {t("library:projectName")}
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="Pan Tadeusz"
                  autoFocus
                  required
                  className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground">
                  {t("library:voiceMode")}
                </label>
                <select
                  value={voiceMode}
                  onChange={(e) => setVoiceMode(e.target.value as VoiceMode)}
                  className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="single">{t("library:voiceModes.single")}</option>
                  <option value="narrator_dialogue">
                    {t("library:voiceModes.narrator_dialogue")}
                  </option>
                  <option value="narrator_male_female">
                    {t("library:voiceModes.narrator_male_female")}
                  </option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground">
                  {t("library:language")}
                </label>
                <input
                  type="text"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
                >
                  {t("library:cancel")}
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || !projectName.trim()}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {createMutation.isPending ? "..." : t("library:create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Ingest Ebook Modal */}
      {ingestProjectId && (
        <IngestModal
          projectId={ingestProjectId}
          isOpen={Boolean(ingestProjectId)}
          onClose={() => setIngestProjectId(null)}
          onSuccess={() => {
            const pid = ingestProjectId;
            setIngestProjectId(null);
            if (onNavigateToEditor && pid) {
              setActiveProjectId(pid);
              onNavigateToEditor(pid);
            }
          }}
        />
      )}
    </div>
  );
}
