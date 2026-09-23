// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "../../components/ui/button";
import type { ChapterItem, EngineApi } from "../../lib/api/client";
import { useEngineApi } from "../../lib/api/context";
import { failureCode } from "../../lib/api/endpoint";
import { translateError } from "../../lib/errors";

const PROJECTS_KEY = ["projects"] as const;

export function ChaptersScreen() {
  const api = useEngineApi();
  const { t } = useTranslation("chapters");
  if (!api) {
    return (
      <Frame>
        <RequestError code="engine.not_ready" />
      </Frame>
    );
  }
  return <ChaptersLoaded api={api} empty={t("empty")}></ChaptersLoaded>;
}

function ChaptersLoaded({ api, empty }: { api: EngineApi; empty: string }) {
  const { t } = useTranslation("chapters");
  const projects = useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () => api.listProjects(),
  });

  if (!projects.data) {
    if (projects.isError) {
      return (
        <Frame>
          <RequestError code={failureCode(projects.error)} />
          <Button onClick={() => void projects.refetch()}>{t("retry")}</Button>
        </Frame>
      );
    }
    return (
      <Frame>
        <p role="status">{t("loading")}</p>
      </Frame>
    );
  }

  const projectId = projects.data.open_project_id;
  if (!projectId) {
    return (
      <Frame>
        <p>{t("no_project")}</p>
        <Link to="/library" className={linkClass}>
          {t("library")}
        </Link>
      </Frame>
    );
  }
  return <ChapterList api={api} projectId={projectId} empty={empty}></ChapterList>;
}

function ChapterList({
  api,
  projectId,
  empty,
}: {
  api: EngineApi;
  projectId: string;
  empty: string;
}) {
  const { t } = useTranslation("chapters");
  const queryClient = useQueryClient();
  const chaptersKey = ["chapters", projectId] as const;
  const list = useQuery({
    queryKey: chaptersKey,
    queryFn: () => api.listChapters(projectId),
  });
  const [titles, setTitles] = useState<Record<string, string>>({});

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: chaptersKey });
  };

  const patch = useMutation({
    mutationFn: (body: { id: string; title?: string; included?: boolean }) =>
      api.patchChapter(body.id, { title: body.title, included: body.included }),
    onSuccess: refresh,
  });

  const reorder = useMutation({
    mutationFn: (order: string[]) => api.reorderChapters(projectId, order),
    onSuccess: refresh,
  });

  if (!list.data) {
    if (list.isError) {
      return (
        <Frame>
          <RequestError code={failureCode(list.error)} />
          <Button onClick={() => void list.refetch()}>{t("retry")}</Button>
        </Frame>
      );
    }
    return (
      <Frame>
        <p role="status">{t("loading")}</p>
      </Frame>
    );
  }

  const chapters = list.data.chapters;
  const busy = patch.isPending || reorder.isPending;

  function move(index: number, delta: number): void {
    const next = chapters.slice();
    const target = index + delta;
    const [item] = next.splice(index, 1);
    if (!item || target < 0 || target >= chapters.length) return;
    next.splice(target, 0, item);
    reorder.mutate(next.map((chapter) => chapter.id));
  }

  function commitTitle(chapter: ChapterItem): void {
    const draft = (titles[chapter.id] ?? chapter.title).trim();
    if (draft.length === 0 || draft === chapter.title) {
      setTitles((current) => {
        const copy = { ...current };
        delete copy[chapter.id];
        return copy;
      });
      return;
    }
    patch.mutate({ id: chapter.id, title: draft });
  }

  return (
    <Frame>
      {chapters.length === 0 ? <p>{empty}</p> : null}
      {patch.isError ? (
        <RequestError code={failureCode(patch.error)}></RequestError>
      ) : null}
      {reorder.isError ? (
        <RequestError code={failureCode(reorder.error)}></RequestError>
      ) : null}
      <ul className="flex flex-col gap-3">
        {chapters.map((chapter, index) => (
          <li
            key={chapter.id}
            className="flex flex-col gap-3 rounded-md border border-line px-4 py-3 dark:border-night-line"
          >
            <label className="flex flex-col gap-1 text-sm text-ink-soft dark:text-dawn-soft">
              {t("rename")}
              <input
                value={titles[chapter.id] ?? chapter.title}
                disabled={busy}
                onChange={(event) =>
                  setTitles((current) => ({ ...current, [chapter.id]: event.target.value }))
                }
                onBlur={() => commitTitle(chapter)}
                className={fieldClass}
              />
            </label>
            <p className="text-sm text-ink-soft dark:text-dawn-soft">
              {t("blocks", { count: chapter.block_count })}
              {" · "}
              {t("audio", { seconds: chapter.est_audio_s })}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-ink dark:text-dawn">
                <input
                  type="checkbox"
                  checked={chapter.included}
                  disabled={busy}
                  onChange={(event) =>
                    patch.mutate({ id: chapter.id, included: event.target.checked })
                  }
                />
                {t("included")}
              </label>
              <Button variant="quiet" disabled={busy || index === 0} onClick={() => move(index, -1)}>
                {t("move_up")}
              </Button>
              <Button
                variant="quiet"
                disabled={busy || index === chapters.length - 1}
                onClick={() => move(index, 1)}
              >
                {t("move_down")}
              </Button>
              <Link to={`/editor?chapter=${encodeURIComponent(chapter.id)}`} className={linkClass}>
                {t("edit")}
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </Frame>
  );
}

const fieldClass =
  "rounded-md border border-line bg-paper px-3 py-1.5 text-base text-ink outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 dark:border-night-line dark:bg-night-2 dark:text-dawn";

const linkClass =
  "inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium text-ink underline decoration-accent underline-offset-4 hover:opacity-80 dark:text-dawn";

function Frame({ children }: { children: ReactNode }) {
  const { t } = useTranslation("chapters");
  return (
    <section className="max-w-3xl">
      <h1 className="font-serif text-3xl tracking-tight text-ink dark:text-dawn">{t("title")}</h1>
      <div className="mt-6 space-y-4">{children}</div>
    </section>
  );
}

function RequestError({ code }: { code: string }) {
  const { t } = useTranslation("chapters");
  const message = translateError((key, options) => t(key, options), code);
  return (
    <div role="alert" className="space-y-2">
      <p className="text-base text-ink dark:text-dawn">{message}</p>
      <p className="text-sm text-ink-soft dark:text-dawn-soft">
        {t("error_code")} <code className="font-mono text-ink dark:text-dawn">{code}</code>
      </p>
    </div>
  );
}
