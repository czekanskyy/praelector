// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Eye,
  FileEdit,
  Loader2,
  Plus,
  Replace,
  Save,
  Search,
  Trash2,
  Volume2,
  X,
} from "lucide-react";
import { api } from "../../lib/api/client";
import { ChapterTree } from "../chapters/ChapterTree";
import { useProjectStore } from "../../stores/projectStore";
import type {
  ReplacePreview,
  ReplaceResponse,
  SearchResponse,
  SpanKind,
  SpanResponse,
} from "@praelector/schemas";

export function EditorScreen(): React.ReactElement {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { activeProjectId, activeChapterId, setActiveChapterId } = useProjectStore();

  const [viewMode, setViewMode] = useState<"display" | "spoken">("display");
  const [editorText, setEditorText] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [baseRevision, setBaseRevision] = useState(1);

  // Search & Replace panel state
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [replacementText, setReplacementText] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [isRegex, setIsRegex] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [replacePreview, setReplacePreview] = useState<ReplaceResponse | null>(null);

  // Spans management
  const [isSpansOpen, setIsSpansOpen] = useState(false);
  const [selectedSpanKind, setSelectedSpanKind] = useState<SpanKind>("skip");
  const [newSpanStart, setNewSpanStart] = useState(0);
  const [newSpanEnd, setNewSpanEnd] = useState(10);
  const [newSpanSpoken, setNewSpanSpoken] = useState("");

  // 1. Fetch project chapters
  const chaptersQuery = useQuery({
    queryKey: ["chapters", activeProjectId],
    queryFn: () => (activeProjectId ? api.listChapters(activeProjectId) : []),
    enabled: Boolean(activeProjectId),
  });

  const chapters = chaptersQuery.data || [];

  // Auto-select first chapter if none selected
  useEffect(() => {
    if (!activeChapterId && chapters.length > 0) {
      setActiveChapterId(chapters[0].id);
    }
  }, [activeChapterId, chapters, setActiveChapterId]);

  // 2. Fetch project details to know current revision
  const projectQuery = useQuery({
    queryKey: ["project", activeProjectId],
    queryFn: () => (activeProjectId ? api.getProject(activeProjectId) : null),
    enabled: Boolean(activeProjectId),
  });

  // 3. Fetch chapter text
  const textQuery = useQuery({
    queryKey: ["chapter-text", activeChapterId, viewMode],
    queryFn: () =>
      activeChapterId ? api.getChapterText(activeChapterId, viewMode) : null,
    enabled: Boolean(activeChapterId),
  });

  // 4. Fetch chapter spans
  const spansQuery = useQuery({
    queryKey: ["chapter-spans", activeChapterId],
    queryFn: () => (activeChapterId ? api.listChapterSpans(activeChapterId) : []),
    enabled: Boolean(activeChapterId),
  });

  // 5. Fetch chapter blocks for manual span reference
  const blocksQuery = useQuery({
    queryKey: ["chapter-blocks", activeChapterId],
    queryFn: () => (activeChapterId ? api.getChapterBlocks(activeChapterId) : []),
    enabled: Boolean(activeChapterId),
  });

  // Sync editor content when textQuery updates and user hasn't typed uncommitted changes
  useEffect(() => {
    if (textQuery.data) {
      setEditorText(textQuery.data.text);
      setIsDirty(false);
      if (projectQuery.data?.current_revision) {
        setBaseRevision(projectQuery.data.current_revision);
      }
    }
  }, [textQuery.data, projectQuery.data]);

  // Save Text Mutation
  const saveMutation = useMutation({
    mutationFn: (text: string) => {
      if (!activeChapterId) throw new Error("No chapter selected");
      return api.updateChapterText(activeChapterId, {
        text,
        base_revision: baseRevision,
      });
    },
    onSuccess: (res) => {
      setIsDirty(false);
      setBaseRevision(res.revision);
      queryClient.invalidateQueries({ queryKey: ["chapter-text", activeChapterId] });
      queryClient.invalidateQueries({ queryKey: ["chapter-spans", activeChapterId] });
      queryClient.invalidateQueries({ queryKey: ["chapters", activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["project", activeProjectId] });
    },
  });

  // Search Mutation
  const searchMutation = useMutation({
    mutationFn: () => {
      if (!activeProjectId) throw new Error("No project");
      return api.searchProject(activeProjectId, {
        query: searchQuery,
        case_sensitive: caseSensitive,
        regex: isRegex,
        scope: "book",
      });
    },
    onSuccess: (data) => setSearchResults(data),
  });

  // Replace Mutation
  const replaceMutation = useMutation({
    mutationFn: (dryRun: boolean) => {
      if (!activeProjectId) throw new Error("No project");
      return api.replaceProject(activeProjectId, {
        query: searchQuery,
        replacement: replacementText,
        case_sensitive: caseSensitive,
        regex: isRegex,
        scope: "book",
        dry_run: dryRun,
      });
    },
    onSuccess: (data, variables) => {
      if (variables) {
        // Dry run preview
        setReplacePreview(data);
      } else {
        // Executed replace
        setReplacePreview(null);
        setSearchResults(null);
        queryClient.invalidateQueries({ queryKey: ["chapter-text", activeChapterId] });
        queryClient.invalidateQueries({ queryKey: ["chapters", activeProjectId] });
        queryClient.invalidateQueries({ queryKey: ["project", activeProjectId] });
      }
    },
  });

  // Delete Span Mutation
  const deleteSpanMutation = useMutation({
    mutationFn: (spanId: string) => api.deleteSpan(spanId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapter-spans", activeChapterId] });
      queryClient.invalidateQueries({ queryKey: ["chapter-text", activeChapterId] });
    },
  });

  // Create Span Mutation
  const createSpanMutation = useMutation({
    mutationFn: () => {
      if (!activeChapterId) throw new Error("No chapter");
      const blocks = blocksQuery.data || [];
      if (blocks.length === 0) throw new Error("No blocks available");
      const firstBlock = blocks[0];

      return api.createSpan(activeChapterId, {
        block_id: firstBlock.id,
        start: newSpanStart,
        end: newSpanEnd,
        kind: selectedSpanKind,
        spoken: newSpanSpoken.trim() ? newSpanSpoken.trim() : null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapter-spans", activeChapterId] });
      queryClient.invalidateQueries({ queryKey: ["chapter-text", activeChapterId] });
      setNewSpanSpoken("");
    },
  });

  const activeChapter = chapters.find((c) => c.id === activeChapterId);
  const spans = spansQuery.data || [];

  if (!activeProjectId) {
    return (
      <div className="flex h-96 flex-col items-center justify-center rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
        <FileEdit className="mb-3 h-10 w-10 text-muted-foreground/40" />
        <p className="text-base font-semibold">Brak otwartego projektu</p>
        <p className="text-sm">Otwórz lub utwórz projekt w zakładce Biblioteka.</p>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-10rem)] w-full overflow-hidden rounded-lg border border-border bg-card">
      {/* Chapter Navigation Sidebar */}
      <div className="w-80 shrink-0 h-full">
        <ChapterTree
          projectId={activeProjectId}
          activeChapterId={activeChapterId}
          onSelectChapter={(cid) => setActiveChapterId(cid)}
        />
      </div>

      {/* Main Editing Column */}
      <div className="flex flex-1 flex-col h-full overflow-hidden bg-background">
        {/* Editor Toolbar */}
        <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2 text-xs">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-sm">
              {activeChapter ? `${activeChapter.ordinal}. ${activeChapter.title}` : "Wybierz rozdział"}
            </span>

            {/* View Mode Toggle */}
            <div className="flex items-center rounded-md border border-border bg-muted p-0.5">
              <button
                type="button"
                onClick={() => setViewMode("display")}
                className={`flex items-center gap-1 rounded px-2.5 py-1 font-medium transition ${
                  viewMode === "display"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Eye className="h-3 w-3" />
                {t("editor:printView")}
              </button>
              <button
                type="button"
                onClick={() => setViewMode("spoken")}
                className={`flex items-center gap-1 rounded px-2.5 py-1 font-medium transition ${
                  viewMode === "spoken"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Volume2 className="h-3 w-3" />
                {t("editor:spokenView")}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Toggle Search/Replace */}
            <button
              type="button"
              onClick={() => setIsSearchOpen(!isSearchOpen)}
              className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 font-medium ${
                isSearchOpen
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              <Search className="h-3.5 w-3.5" />
              {t("editor:findReplace")}
            </button>

            {/* Toggle Spans Panel */}
            <button
              type="button"
              onClick={() => setIsSpansOpen(!isSpansOpen)}
              className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 font-medium ${
                isSpansOpen
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              Adnotacje ({spans.length})
            </button>

            {/* Save Button */}
            {viewMode === "display" && (
              <button
                type="button"
                onClick={() => saveMutation.mutate(editorText)}
                disabled={!isDirty || saveMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {saveMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                {saveMutation.isPending ? t("editor:saving") : t("common:actions.save")}
              </button>
            )}
          </div>
        </div>

        {/* Search & Replace Floating Bar */}
        {isSearchOpen && (
          <div className="border-b border-border bg-muted/40 p-3 space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 flex-1">
                <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("editor:find")}
                  className="w-full rounded border border-input bg-background px-2 py-1 outline-none focus:border-primary"
                />
              </div>

              <div className="flex items-center gap-1 flex-1">
                <Replace className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <input
                  type="text"
                  value={replacementText}
                  onChange={(e) => setReplacementText(e.target.value)}
                  placeholder={t("editor:replace")}
                  className="w-full rounded border border-input bg-background px-2 py-1 outline-none focus:border-primary"
                />
              </div>

              <button
                type="button"
                onClick={() => searchMutation.mutate()}
                disabled={!searchQuery.trim() || searchMutation.isPending}
                className="rounded bg-secondary px-2.5 py-1 font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
              >
                Szukaj
              </button>

              <button
                type="button"
                onClick={() => replaceMutation.mutate(true)}
                disabled={!searchQuery.trim() || replaceMutation.isPending}
                className="rounded border border-border px-2.5 py-1 font-medium hover:bg-muted disabled:opacity-50"
              >
                Podgląd
              </button>

              <button
                type="button"
                onClick={() => replaceMutation.mutate(false)}
                disabled={!searchQuery.trim() || replaceMutation.isPending}
                className="rounded bg-primary px-2.5 py-1 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {t("editor:replaceAll")}
              </button>

              <button
                type="button"
                onClick={() => setIsSearchOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex items-center gap-4 text-muted-foreground">
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={caseSensitive}
                  onChange={(e) => setCaseSensitive(e.target.checked)}
                />
                Wielkość liter
              </label>
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isRegex}
                  onChange={(e) => setIsRegex(e.target.checked)}
                />
                Regex
              </label>

              {searchResults && (
                <span className="font-semibold text-foreground">
                  Dopasowań: {searchResults.count}
                </span>
              )}

              {replacePreview && (
                <span className="font-semibold text-primary">
                  Proponowanych zamian: {replacePreview.count}
                </span>
              )}
            </div>

            {/* Replace previews list */}
            {Boolean(replacePreview?.previews && replacePreview.previews.length > 0) && (
              <div className="max-h-32 overflow-y-auto rounded border border-border/80 bg-background p-2 space-y-1">
                {(replacePreview?.previews ?? []).map((p: ReplacePreview, idx: number) => (
                  <div key={idx} className="flex items-center justify-between text-[11px]">
                    <span className="text-destructive truncate line-through max-w-[45%]">
                      {p.original}
                    </span>
                    <span className="text-muted-foreground">→</span>
                    <span className="text-green-600 dark:text-green-400 truncate max-w-[45%]">
                      {p.proposed}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Editor Body */}
        <div className="flex flex-1 overflow-hidden relative">
          <div className="flex-1 overflow-y-auto p-6 font-serif text-base leading-relaxed">
            {viewMode === "display" ? (
              <textarea
                value={editorText}
                onChange={(e) => {
                  setEditorText(e.target.value);
                  setIsDirty(true);
                }}
                placeholder="Wpisz treść rozdziału..."
                className="h-full w-full resize-none border-none bg-transparent outline-none leading-relaxed text-foreground placeholder:text-muted-foreground/40 font-serif"
              />
            ) : (
              <div className="whitespace-pre-wrap select-text text-foreground/90 font-serif">
                {editorText || "Brak tekstu w widoku lektorskim"}
              </div>
            )}
          </div>

          {/* Spans Sidebar Drawer */}
          {isSpansOpen && (
            <div className="w-80 border-l border-border bg-card flex flex-col h-full text-xs">
              <div className="flex items-center justify-between border-b border-border p-3">
                <span className="font-semibold">Adnotacje i wymowa (Spans)</span>
                <button
                  type="button"
                  onClick={() => setIsSpansOpen(false)}
                  className="rounded p-1 text-muted-foreground hover:bg-muted"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Add Span form */}
              <div className="p-3 border-b border-border bg-muted/20 space-y-2">
                <p className="font-medium text-[11px] text-muted-foreground">
                  Dodaj manualną adnotację
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-muted-foreground">Typ</label>
                    <select
                      value={selectedSpanKind}
                      onChange={(e) => setSelectedSpanKind(e.target.value as SpanKind)}
                      className="w-full rounded border border-input bg-background px-1.5 py-1"
                    >
                      <option value="skip">Pomiń (skip)</option>
                      <option value="dialogue">Dialog</option>
                      <option value="pronunciation">Wymowa</option>
                      <option value="pause">Pauza</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">Wymowa (opcjonalnie)</label>
                    <input
                      type="text"
                      value={newSpanSpoken}
                      onChange={(e) => setNewSpanSpoken(e.target.value)}
                      placeholder="Tekst fonetyczny"
                      className="w-full rounded border border-input bg-background px-1.5 py-1"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-muted-foreground">Początek (znak)</label>
                    <input
                      type="number"
                      value={newSpanStart}
                      onChange={(e) => setNewSpanStart(parseInt(e.target.value) || 0)}
                      className="w-full rounded border border-input bg-background px-1.5 py-1"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">Koniec (znak)</label>
                    <input
                      type="number"
                      value={newSpanEnd}
                      onChange={(e) => setNewSpanEnd(parseInt(e.target.value) || 0)}
                      className="w-full rounded border border-input bg-background px-1.5 py-1"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => createSpanMutation.mutate()}
                  disabled={createSpanMutation.isPending}
                  className="w-full inline-flex items-center justify-center gap-1 rounded bg-secondary px-2 py-1 font-medium text-secondary-foreground hover:bg-secondary/80"
                >
                  <Plus className="h-3 w-3" />
                  Dodaj adnotację
                </button>
              </div>

              {/* Spans List */}
              <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                {spans.length === 0 ? (
                  <p className="p-4 text-center text-muted-foreground">Brak adnotacji w tym rozdziale.</p>
                ) : (
                  spans.map((s: SpanResponse) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between rounded border border-border bg-background p-2"
                    >
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`rounded px-1 py-0.2 text-[9px] font-bold uppercase ${
                              s.kind === "skip"
                                ? "bg-destructive/15 text-destructive"
                                : s.kind === "dialogue"
                                ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                                : "bg-primary/15 text-primary"
                            }`}
                          >
                            {s.kind}
                          </span>
                          <span className="font-mono text-[10px] text-muted-foreground">
                            [{s.start}..{s.end}]
                          </span>
                        </div>
                        {s.spoken && (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Wymowa: <em>{s.spoken}</em>
                          </p>
                        )}
                        <span className="text-[9px] text-muted-foreground/60">{s.origin}</span>
                      </div>

                      <button
                        type="button"
                        onClick={() => deleteSpanMutation.mutate(s.id)}
                        className="rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        title="Usuń adnotację"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
