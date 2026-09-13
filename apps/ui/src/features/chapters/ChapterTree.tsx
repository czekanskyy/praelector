// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  ArrowDown,
  ArrowUp,
  Check,
  Clock,
  Edit2,
  FileText,
  GitMerge,
  X,
} from "lucide-react";
import { api } from "../../lib/api/client";
import type { ChapterResponse } from "@praelector/schemas";

interface ChapterTreeProps {
  projectId: string;
  activeChapterId: string | null;
  onSelectChapter: (chapterId: string) => void;
}

export function ChapterTree({
  projectId,
  activeChapterId,
  onSelectChapter,
}: ChapterTreeProps): React.ReactElement {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [editingChapterId, setEditingChapterId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [selectedMergeIds, setSelectedMergeIds] = useState<string[]>([]);

  const chaptersQuery = useQuery({
    queryKey: ["chapters", projectId],
    queryFn: () => api.listChapters(projectId),
    enabled: Boolean(projectId),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { title?: string; included?: boolean } }) =>
      api.updateChapter(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", projectId] });
      setEditingChapterId(null);
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (order: string[]) => api.reorderChapters(projectId, { order }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", projectId] });
    },
  });

  const mergeMutation = useMutation({
    mutationFn: (ids: string[]) => api.mergeChapters(projectId, { ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chapters", projectId] });
      setSelectedMergeIds([]);
    },
  });

  const chapters = chaptersQuery.data || [];

  const handleToggleIncluded = (chapter: ChapterResponse, e: React.MouseEvent) => {
    e.stopPropagation();
    updateMutation.mutate({
      id: chapter.id,
      data: { included: !chapter.included },
    });
  };

  const handleStartRename = (chapter: ChapterResponse, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingChapterId(chapter.id);
    setEditingTitle(chapter.title);
  };

  const handleSaveRename = (chapterId: string) => {
    if (!editingTitle.trim()) return;
    updateMutation.mutate({
      id: chapterId,
      data: { title: editingTitle.trim() },
    });
  };

  const handleMove = (index: number, direction: "up" | "down", e: React.MouseEvent) => {
    e.stopPropagation();
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= chapters.length) return;

    const newOrder = [...chapters.map((c) => c.id)];
    const temp = newOrder[index];
    newOrder[index] = newOrder[newIndex];
    newOrder[newIndex] = temp;

    reorderMutation.mutate(newOrder);
  };

  const toggleMergeSelect = (chapterId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedMergeIds((prev) =>
      prev.includes(chapterId) ? prev.filter((id) => id !== chapterId) : [...prev, chapterId]
    );
  };

  const handleMergeSelected = () => {
    if (selectedMergeIds.length < 2) return;
    mergeMutation.mutate(selectedMergeIds);
  };

  const formatAudioTime = (seconds?: number) => {
    if (!seconds) return "0 min";
    const mins = Math.ceil(seconds / 60);
    return `~${mins} min`;
  };

  return (
    <div className="flex h-full flex-col border-r border-border bg-card">
      <div className="flex items-center justify-between border-b border-border p-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">{t("chapters:title")}</h3>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {chapters.length}
          </span>
        </div>

        {selectedMergeIds.length >= 2 && (
          <button
            onClick={handleMergeSelected}
            disabled={mergeMutation.isPending}
            className="inline-flex items-center gap-1 rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            <GitMerge className="h-3 w-3" />
            {t("chapters:merge")} ({selectedMergeIds.length})
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {chapters.length === 0 ? (
          <p className="p-4 text-center text-xs text-muted-foreground">
            {t("chapters:noChapters")}
          </p>
        ) : (
          chapters.map((chapter, index) => {
            const isSelected = activeChapterId === chapter.id;
            const isEditing = editingChapterId === chapter.id;
            const isMergeChecked = selectedMergeIds.includes(chapter.id);

            return (
              <div
                key={chapter.id}
                onClick={() => onSelectChapter(chapter.id)}
                className={`group flex flex-col rounded-md border p-2.5 text-xs cursor-pointer transition-colors ${
                  isSelected
                    ? "border-primary bg-primary/10 text-foreground"
                    : chapter.included === false
                    ? "border-border/50 bg-muted/30 text-muted-foreground opacity-60"
                    : "border-border bg-background hover:border-primary/40 hover:bg-muted/40 text-foreground"
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  {/* Checkbox for merge + Ordinal */}
                  <div className="flex items-center gap-1.5 flex-1 min-w-0">
                    <input
                      type="checkbox"
                      checked={isMergeChecked}
                      onClick={(e) => toggleMergeSelect(chapter.id, e)}
                      onChange={() => {}}
                      className="rounded border-border"
                      title="Zaznacz do połączenia"
                    />
                    <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                      #{chapter.ordinal}
                    </span>

                    {/* Title or Inline Edit */}
                    {isEditing ? (
                      <div
                        className="flex items-center gap-1 flex-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="text"
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveRename(chapter.id);
                            if (e.key === "Escape") setEditingChapterId(null);
                          }}
                          autoFocus
                          className="w-full rounded border border-primary bg-background px-1.5 py-0.5 text-xs outline-none"
                        />
                        <button
                          onClick={() => handleSaveRename(chapter.id)}
                          className="rounded p-0.5 text-green-500 hover:bg-green-500/10"
                        >
                          <Check className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => setEditingChapterId(null)}
                          className="rounded p-0.5 text-muted-foreground hover:bg-muted"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ) : (
                      <span className="truncate font-medium">{chapter.title}</span>
                    )}
                  </div>

                  {/* Actions on hover */}
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                    {!isEditing && (
                      <button
                        onClick={(e) => handleStartRename(chapter, e)}
                        className="rounded p-1 text-muted-foreground hover:text-foreground"
                        title={t("chapters:rename")}
                      >
                        <Edit2 className="h-3 w-3" />
                      </button>
                    )}
                    <button
                      onClick={(e) => handleMove(index, "up", e)}
                      disabled={index === 0}
                      className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-20"
                      title="Przesuń w górę"
                    >
                      <ArrowUp className="h-3 w-3" />
                    </button>
                    <button
                      onClick={(e) => handleMove(index, "down", e)}
                      disabled={index === chapters.length - 1}
                      className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-20"
                      title="Przesuń w dół"
                    >
                      <ArrowDown className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                {/* Details Footer: stats & include toggle */}
                <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/40">
                  <div className="flex items-center gap-2">
                    <span>{chapter.char_count || 0} zn.</span>
                    <span className="flex items-center gap-0.5">
                      <Clock className="h-2.5 w-2.5" />
                      {formatAudioTime(chapter.est_audio_s)}
                    </span>
                  </div>

                  <button
                    onClick={(e) => handleToggleIncluded(chapter, e)}
                    className={`rounded px-1.5 py-0.5 font-medium text-[10px] ${
                      chapter.included !== false
                        ? "bg-primary/15 text-primary"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {chapter.included !== false ? "W nagraniu" : "Pomiń"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
