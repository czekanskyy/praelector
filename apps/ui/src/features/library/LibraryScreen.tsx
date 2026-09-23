// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { Button } from "../../components/ui/button";
import type { EngineApi, ProjectSummary } from "../../lib/api/client";
import { useEngineApi } from "../../lib/api/context";
import { failureCode } from "../../lib/api/endpoint";
import { translateError } from "../../lib/errors";

const PROJECTS_KEY = ["projects"] as const;

export function LibraryScreen() {
  const api = useEngineApi();
  if (!api) {
    return (
      <LibraryFrame>
        <RequestError code="engine.not_ready" />
      </LibraryFrame>
    );
  }
  return <LibraryLoaded api={api}></LibraryLoaded>;
}

function LibraryLoaded({ api }: { api: EngineApi }) {
  const { t, i18n } = useTranslation("library");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const seenApi = useRef(api);

  const list = useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () => api.listProjects(),
  });

  // A replaced client means a new loopback endpoint. Drop the previous list.
  useEffect(() => {
    if (seenApi.current === api) return;
    seenApi.current = api;
    void queryClient.invalidateQueries({ queryKey: PROJECTS_KEY });
  }, [api, queryClient]);

  const create = useMutation({
    mutationFn: (projectName: string) => api.createProject(projectName),
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: PROJECTS_KEY });
    },
  });

  const open = useMutation({
    mutationFn: (id: string) => api.openProject(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: PROJECTS_KEY });
      navigate("/chapters");
    },
  });

  if (!list.data) {
    if (list.isError) {
      return (
        <LibraryFrame>
          <RequestError code={failureCode(list.error)} />
          <Button onClick={() => void list.refetch()}>{t("retry")}</Button>
        </LibraryFrame>
      );
    }
    return (
      <LibraryFrame>
        <p role="status" className="text-base text-ink-soft dark:text-dawn-soft">
          {t("loading")}
        </p>
      </LibraryFrame>
    );
  }

  const data = list.data;
  const busy = create.isPending || open.isPending;

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(name.trim());
  }

  return (
    <LibraryFrame>
      <form noValidate className="flex flex-wrap items-end gap-3" onSubmit={onSubmit}>
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm text-ink-soft dark:text-dawn-soft">
          {t("create_name")}
          <input
            name="name"
            value={name}
            maxLength={200}
            autoComplete="off"
            disabled={busy}
            aria-invalid={create.isError}
            placeholder={t("create_placeholder")}
            onChange={(event) => setName(event.target.value)}
            className="rounded-md border border-line bg-paper px-3 py-1.5 text-base text-ink outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 dark:border-night-line dark:bg-night-2 dark:text-dawn"
          />
        </label>
        <Button type="submit" disabled={busy}>
          {create.isPending ? t("create_pending") : t("create_submit")}
        </Button>
      </form>
      {create.isError ? (
        <RequestError code={failureCode(create.error)}></RequestError>
      ) : null}
      {data.projects.length === 0 ? (
        <div className="max-w-xl">
          <p className="text-base text-ink-soft dark:text-dawn-soft">{t("empty")}</p>
          <p className="mt-2 break-all text-base text-ink-soft dark:text-dawn-soft">
            {t("empty_dir", { path: data.projects_dir })}
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.projects.map((project) => (
            <li key={project.id}>
              <ProjectRow
                project={project}
                locale={i18n.language}
                disabled={busy}
                onOpen={(id) => open.mutate(id)}
              />
            </li>
          ))}
        </ul>
      )}
      {open.isPending ? (
        <p role="status" className="text-sm text-ink-soft dark:text-dawn-soft">
          {t("open_pending")}
        </p>
      ) : null}
      {open.isError ? (
        <RequestError code={failureCode(open.error)}></RequestError>
      ) : null}
    </LibraryFrame>
  );
}

function ProjectRow({
  project,
  locale,
  disabled,
  onOpen,
}: {
  project: ProjectSummary;
  locale: string;
  disabled: boolean;
  onOpen: (id: string) => void;
}) {
  const { t } = useTranslation("library");
  const updated = formatUpdated(project.updated_at, locale);
  const body = (
    <>
      <span className="text-base font-medium text-ink dark:text-dawn">{project.name}</span>
      <span className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          {t("spoken_language")} {spokenLanguageLabel(t, project.spoken_language)}
        </span>
        <span>
          {t("updated")} {updated ?? t("updated_unknown")}
        </span>
      </span>
      {project.is_open || project.unreadable ? (
        <span className="flex flex-wrap gap-2">
          {project.is_open ? (
            <span className="rounded-full bg-accent px-2 py-0.5 text-xs text-accent-fg dark:bg-ember dark:text-ember-fg">
              {t("status_open")}
            </span>
          ) : null}
          {project.unreadable ? (
            <span className="rounded-full border border-line px-2 py-0.5 text-xs dark:border-night-line">
              {t("status_unreadable")}
            </span>
          ) : null}
        </span>
      ) : null}
    </>
  );
  const className =
    "flex w-full flex-col items-start gap-1 rounded-md border border-line px-4 py-3 text-left text-sm text-ink-soft dark:border-night-line dark:text-dawn-soft";

  if (project.unreadable) {
    return <div className={`${className} opacity-80`}>{body}</div>;
  }

  return (
    <button
      type="button"
      className={`${className} hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 dark:hover:bg-night-2`}
      disabled={disabled}
      onClick={() => onOpen(project.id)}
    >
      {body}
    </button>
  );
}

function LibraryFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation("library");
  return (
    <section className="max-w-3xl">
      <h1 className="font-serif text-3xl tracking-tight text-ink dark:text-dawn">{t("title")}</h1>
      <div className="mt-6 space-y-6">{children}</div>
    </section>
  );
}

function RequestError({ code }: { code: string }) {
  const { t } = useTranslation("library");
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

function spokenLanguageLabel(t: (key: string) => string, code: string): string {
  if (code === "pl") return t("language_pl");
  if (code === "en") return t("language_en");
  return code;
}

function formatUpdated(value: string | null, locale: string): string | null {
  if (value === null) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
