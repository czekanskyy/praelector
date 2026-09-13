// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AlertOctagon,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileUp,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import { api } from "../../lib/api/client";
import type { IngestProbeResponse } from "@praelector/schemas";

interface IngestModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function IngestModal({
  projectId,
  isOpen,
  onClose,
  onSuccess,
}: IngestModalProps): React.ReactElement | null {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [filePath, setFilePath] = useState("");
  const [probeResult, setProbeResult] = useState<IngestProbeResponse | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [isProbing, setIsProbing] = useState(false);

  const probeMutation = useMutation({
    mutationFn: (path: string) => api.probeIngest(projectId, { path }),
    onSuccess: (data) => {
      setProbeResult(data);
      setProbeError(null);
      setIsProbing(false);
    },
    onError: (err: Error) => {
      setProbeError(err.message);
      setProbeResult(null);
      setIsProbing(false);
    },
  });

  const importMutation = useMutation({
    mutationFn: (path: string) =>
      api.importIngest(projectId, {
        path,
        convert: { enabled: true, engine: "calibre" },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["project-source", projectId] });
      onClose();
      onSuccess?.();
    },
  });

  if (!isOpen) return null;

  const handleSelectFile = async () => {
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({
        multiple: false,
        filters: [
          {
            name: "Ebooks",
            extensions: ["epub", "pdf", "mobi", "azw3", "azw"],
          },
        ],
      });
      if (selected && typeof selected === "string") {
        setFilePath(selected);
        triggerProbe(selected);
      }
    } catch {
      // Browser fallback - user enters path manually
    }
  };

  const triggerProbe = (path: string) => {
    if (!path.trim()) return;
    setIsProbing(true);
    setProbeResult(null);
    setProbeError(null);
    probeMutation.mutate(path.trim());
  };

  const handleImport = () => {
    if (!filePath || !probeResult || probeResult.drm?.detected || probeResult.has_text_layer === false) {
      return;
    }
    importMutation.mutate(filePath);
  };

  const isDrmDetected = probeResult?.drm?.detected;
  const isNoTextLayer = probeResult?.has_text_layer === false;
  const canImport =
    Boolean(probeResult) &&
    !isDrmDetected &&
    !isNoTextLayer &&
    !importMutation.isPending &&
    !isProbing;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-lg border border-border bg-card p-6 shadow-2xl animate-in fade-in-50 zoom-in-95">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-primary" />
            <h3 className="text-lg font-semibold">{t("ingest:title")}</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-4 space-y-4">
          {/* File Picker / Dropzone */}
          <div
            onClick={handleSelectFile}
            className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border p-6 text-center cursor-pointer transition hover:border-primary/60 hover:bg-primary/5"
          >
            <UploadCloud className="h-10 w-10 text-muted-foreground mb-2" />
            <p className="text-sm font-medium">{t("ingest:dropzone")}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t("ingest:formatsNotice")}
            </p>
            <button
              type="button"
              className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80"
            >
              <FileUp className="h-3.5 w-3.5" />
              {t("ingest:selectFile")}
            </button>
          </div>

          {/* Manual Path Input (Fall back / display) */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Ścieżka do pliku / File path
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="C:\e-books\ksiazka.epub"
                className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-primary"
              />
              <button
                type="button"
                onClick={() => triggerProbe(filePath)}
                disabled={!filePath.trim() || isProbing}
                className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
              >
                {isProbing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Sprawdź (Probe)"
                )}
              </button>
            </div>
          </div>

          {/* Error Probe Banner */}
          {probeError && (
            <div className="flex items-start gap-2.5 rounded-md bg-destructive/10 p-3 text-xs text-destructive border border-destructive/20">
              <AlertOctagon className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Błąd weryfikacji pliku</p>
                <p>{probeError}</p>
              </div>
            </div>
          )}

          {/* DRM Refusal Alert */}
          {isDrmDetected && (
            <div className="flex items-start gap-2.5 rounded-md bg-destructive/10 p-3 text-xs text-destructive border border-destructive/30">
              <AlertOctagon className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-sm">Odmowa: Wykryto zabezpieczenie DRM</p>
                <p className="mt-1">
                  {t("ingest:drmWarning")} ({probeResult?.drm?.reason || "Wykryto szyfrowanie"})
                </p>
                <p className="mt-1 text-muted-foreground">
                  Zgodnie z zasadą bezpieczeństwa, pliki DRM nie są odszyfrowywane ani importowane.
                </p>
              </div>
            </div>
          )}

          {/* No Text Layer Alert */}
          {isNoTextLayer && (
            <div className="flex items-start gap-2.5 rounded-md bg-amber-500/10 p-3 text-xs text-amber-600 dark:text-amber-400 border border-amber-500/30">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">Brak warstwy tekstowej (skan)</p>
                <p className="mt-1">
                  Ten dokument PDF nie zawiera odczytywalnego tekstu. Wersja v1 nie wspiera OCR.
                </p>
              </div>
            </div>
          )}

          {/* Metadata Preview Card */}
          {probeResult && !isDrmDetected && !isNoTextLayer && (
            <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-2 text-xs">
              <div className="flex items-center gap-2 text-green-600 dark:text-green-400 font-semibold">
                <CheckCircle2 className="h-4 w-4" />
                <span>Plik poprawny ({probeResult.format.toUpperCase()})</span>
              </div>
              {probeResult.metadata_preview && (
                <div className="grid grid-cols-2 gap-2 pt-1 border-t border-border/60">
                  <div>
                    <span className="text-muted-foreground">Tytuł:</span>{" "}
                    <strong>{probeResult.metadata_preview.title}</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Autor:</span>{" "}
                    <strong>
                      {probeResult.metadata_preview.authors?.join(", ") || "Nieznany"}
                    </strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Język:</span>{" "}
                    <strong>{probeResult.metadata_preview.language}</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Rozdziałów:</span>{" "}
                    <strong>{probeResult.metadata_preview.chapter_count || "~"}</strong>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="mt-6 flex items-center justify-end gap-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            {t("common:actions.cancel")}
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={!canImport}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {importMutation.isPending && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            {importMutation.isPending ? t("ingest:importing") : "Zaimportuj e-book"}
          </button>
        </div>
      </div>
    </div>
  );
}
