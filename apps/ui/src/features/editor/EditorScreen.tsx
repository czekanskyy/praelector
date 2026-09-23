// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { search, searchKeymap } from "@codemirror/search";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { Button } from "../../components/ui/button";
import type { EngineApi, TextView } from "../../lib/api/client";
import { useEngineApi } from "../../lib/api/context";
import { failureCode } from "../../lib/api/endpoint";
import { translateError } from "../../lib/errors";

const PROJECTS_KEY = ["projects"] as const;
const SAVE_DELAY_MS = 400;

export function EditorScreen() {
  const api = useEngineApi();
  const { t } = useTranslation("editor");
  const [params] = useSearchParams();
  const chapterId = params.get("chapter");
  if (!api) {
    return (
      <Frame>
        <RequestError code="engine.not_ready" />
      </Frame>
    );
  }
  if (!chapterId) {
    return (
      <Frame>
        <p>{t("empty")}</p>
        <Link to="/chapters" className={linkClass}>
          {t("back")}
        </Link>
      </Frame>
    );
  }
  return <EditorLoaded api={api} chapterId={chapterId}></EditorLoaded>;
}

function EditorLoaded({ api, chapterId }: { api: EngineApi; chapterId: string }) {
  const { t } = useTranslation("editor");
  const [view, setView] = useState<TextView>("display");
  const [generation, setGeneration] = useState(0);
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

  return (
    <ChapterEditor
      api={api}
      projectId={projectId}
      chapterId={chapterId}
      view={view}
      generation={generation}
      onView={setView}
      onReplaced={() => setGeneration((current) => current + 1)}
    ></ChapterEditor>
  );
}

function ChapterEditor({
  api,
  projectId,
  chapterId,
  view,
  generation,
  onView,
  onReplaced,
}: {
  api: EngineApi;
  projectId: string;
  chapterId: string;
  view: TextView;
  generation: number;
  onView: (view: TextView) => void;
  onReplaced: () => void;
}) {
  const { t } = useTranslation("editor");
  const loaded = useQuery({
    queryKey: ["chapter-text", projectId, chapterId, generation],
    queryFn: () => api.getChapterText(chapterId, "display"),
  });
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [matches, setMatches] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const count = useMutation({
    mutationFn: () =>
      api.replaceText(projectId, {
        query,
        replacement,
        dry_run: true,
        chapter_id: chapterId,
        all_chapters: false,
      }),
    onSuccess: (result) => setMatches(result.count),
  });

  const apply = useMutation({
    mutationFn: () =>
      api.replaceText(projectId, {
        query,
        replacement,
        dry_run: false,
        chapter_id: chapterId,
        all_chapters: false,
      }),
    onSuccess: (result) => {
      setMatches(result.count);
      onReplaced();
    },
  });

  if (!loaded.data) {
    if (loaded.isError) {
      return (
        <Frame>
          <RequestError code={failureCode(loaded.error)} />
          <Button onClick={() => void loaded.refetch()}>{t("retry")}</Button>
        </Frame>
      );
    }
    return (
      <Frame>
        <p role="status">{t("loading")}</p>
      </Frame>
    );
  }

  const text = loaded.data;
  return (
    <Frame>
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/chapters" className={linkClass}>
          {t("back")}
        </Link>
        <span className="text-sm text-ink-soft dark:text-dawn-soft">{t("view_label")}</span>
        <Button
          variant={view === "display" ? "primary" : "quiet"}
          aria-pressed={view === "display"}
          onClick={() => onView("display")}
        >
          {t("view_print")}
        </Button>
        <Button
          variant={view === "spoken" ? "primary" : "quiet"}
          aria-pressed={view === "spoken"}
          onClick={() => onView("spoken")}
        >
          {t("view_spoken")}
        </Button>
      </div>
      <p className="text-sm text-ink-soft dark:text-dawn-soft">
        {view === "display" ? t("view_print_note") : t("view_spoken_note")}
      </p>
      <PlainTextEditor
        key={`${chapterId}:${text.revision}:${generation}`}
        api={api}
        chapterId={chapterId}
        initialText={text.text}
        initialRevision={text.revision}
        onStatus={(status, code) => {
          setSaveState(status);
          setSaveError(code);
        }}
      ></PlainTextEditor>
      <p role="status" className="text-sm text-ink-soft dark:text-dawn-soft">
        {saveState === "saving" ? t("saving") : null}
        {saveState === "saved" ? t("saved") : null}
        {saveState === "failed" ? t("save_failed") : null}
      </p>
      {saveError ? <RequestError code={saveError}></RequestError> : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          count.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-sm text-ink-soft dark:text-dawn-soft">
          {t("find_query")}
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className={fieldClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink-soft dark:text-dawn-soft">
          {t("find_replacement")}
          <input
            value={replacement}
            onChange={(event) => setReplacement(event.target.value)}
            className={fieldClass}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={query.length === 0 || count.isPending}>
            {count.isPending ? t("find_pending") : t("find_count")}
          </Button>
          <Button
            variant="quiet"
            disabled={query.length === 0 || apply.isPending}
            onClick={() => apply.mutate()}
          >
            {t("find_apply")}
          </Button>
        </div>
      </form>
      {matches !== null ? <p role="status">{t("find_result", { count: matches })}</p> : null}
      {count.isError ? <RequestError code={failureCode(count.error)}></RequestError> : null}
      {apply.isError ? <RequestError code={failureCode(apply.error)}></RequestError> : null}
    </Frame>
  );
}

function PlainTextEditor({
  api,
  chapterId,
  initialText,
  initialRevision,
  onStatus,
}: {
  api: EngineApi;
  chapterId: string;
  initialText: string;
  initialRevision: number;
  onStatus: (status: "idle" | "saving" | "saved" | "failed", code: string | null) => void;
}) {
  const { t, i18n } = useTranslation("editor");
  const host = useRef<HTMLDivElement>(null);
  const onStatusRef = useRef(onStatus);
  const translateRef = useRef(t);
  onStatusRef.current = onStatus;
  translateRef.current = t;

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    let alive = true;
    let timer: number | null = null;
    let savedText = initialText;
    let base = initialRevision;
    const latest = { text: initialText };
    const phrases = searchPhrases((key) => translateRef.current(key));

    async function persist(text: string): Promise<void> {
      if (text === savedText) return;
      if (alive) onStatusRef.current("saving", null);
      try {
        const result = await api.putChapterText(chapterId, text, base);
        base = result.revision;
        savedText = text;
        if (alive) onStatusRef.current("saved", null);
      } catch (error) {
        if (alive) onStatusRef.current("failed", failureCode(error));
      }
    }

    const view = new EditorView({
      parent,
      state: EditorState.create({
        doc: initialText,
        extensions: [
          lineNumbers(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
          search({ top: true }),
          EditorState.phrases.of(phrases),
          EditorView.lineWrapping,
          EditorView.theme({
            "&": { backgroundColor: "transparent", color: "inherit" },
            ".cm-content": { fontFamily: "inherit", minHeight: "16rem" },
            ".cm-gutters": { backgroundColor: "transparent", color: "inherit", border: "none" },
            "&.cm-focused": { outline: "none" },
          }),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            latest.text = update.state.doc.toString();
            if (timer !== null) window.clearTimeout(timer);
            timer = window.setTimeout(() => {
              timer = null;
              void persist(latest.text);
            }, SAVE_DELAY_MS);
          }),
        ],
      }),
    });

    return () => {
      alive = false;
      if (timer !== null) {
        window.clearTimeout(timer);
        void persist(latest.text);
      }
      view.destroy();
    };
  }, [api, chapterId, i18n.language, initialRevision, initialText]);

  return (
    <div
      ref={host}
      className="overflow-hidden rounded-md border border-line bg-paper dark:border-night-line dark:bg-night"
    ></div>
  );
}

function searchPhrases(t: (key: string) => string): Record<string, string> {
  return {
    Find: t("cm_find"),
    Replace: t("cm_replace"),
    next: t("cm_next"),
    previous: t("cm_previous"),
    all: t("cm_all"),
    "match case": t("cm_match_case"),
    regexp: t("cm_regexp"),
    "by word": t("cm_by_word"),
    replace: t("cm_replace_one"),
    "replace all": t("cm_replace_all"),
    close: t("cm_close"),
    "Go to line": t("cm_go_to_line"),
    go: t("cm_go"),
    "current match": t("cm_current_match"),
    "on line": t("cm_on_line"),
    "replaced match on line $": t("cm_replaced_one"),
    "replaced $ matches": t("cm_replaced_many"),
  };
}

const fieldClass =
  "rounded-md border border-line bg-paper px-3 py-1.5 text-base text-ink outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 dark:border-night-line dark:bg-night-2 dark:text-dawn";

const linkClass =
  "inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium text-ink underline decoration-accent underline-offset-4 hover:opacity-80 dark:text-dawn";

function Frame({ children }: { children: ReactNode }) {
  const { t } = useTranslation("editor");
  return (
    <section className="max-w-3xl">
      <h1 className="font-serif text-3xl tracking-tight text-ink dark:text-dawn">{t("title")}</h1>
      <div className="mt-6 space-y-4">{children}</div>
    </section>
  );
}

function RequestError({ code }: { code: string }) {
  const { t } = useTranslation("editor");
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
