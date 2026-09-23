// SPDX-License-Identifier: Apache-2.0
import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { Button } from "../../components/ui/button";
import type { EngineApi } from "../../lib/api/client";
import { useEngineApi } from "../../lib/api/context";
import { EngineRequestError, failureCode } from "../../lib/api/endpoint";
import { translateError } from "../../lib/errors";

const PROJECTS_KEY = ["projects"] as const;

export function IngestScreen() {
  const api = useEngineApi();
  const { t } = useTranslation("ingest");
  if (!api) {
    return (
      <Frame>
        <RequestError code="engine.not_ready" />
      </Frame>
    );
  }
  return <IngestLoaded api={api} hint={t("empty")}></IngestLoaded>;
}

function IngestLoaded({ api, hint }: { api: EngineApi; hint: string }) {
  const { t } = useTranslation("ingest");
  const navigate = useNavigate();
  const [path, setPath] = useState("");
  const projects = useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () => api.listProjects(),
  });

  const commit = useMutation({
    mutationFn: (filePath: string) => {
      const projectId = projects.data?.open_project_id;
      if (!projectId) return Promise.reject(new EngineRequestError("project.not_open"));
      return api.commitIngest(projectId, filePath);
    },
    onSuccess: () => navigate("/chapters"),
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

  if (!projects.data.open_project_id) {
    return (
      <Frame>
        <p>{t("no_project")}</p>
        <Link to="/library" className={linkClass}>
          {t("library")}
        </Link>
      </Frame>
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    commit.mutate(path.trim());
  }

  return (
    <Frame>
      <p className="text-base text-ink-soft dark:text-dawn-soft">{hint}</p>
      <form noValidate className="flex flex-col gap-3" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1 text-sm text-ink-soft dark:text-dawn-soft">
          {t("path_label")}
          <input
            name="path"
            value={path}
            autoComplete="off"
            disabled={commit.isPending}
            placeholder={t("path_placeholder")}
            onChange={(event) => setPath(event.target.value)}
            className="rounded-md border border-line bg-paper px-3 py-1.5 text-base text-ink outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 dark:border-night-line dark:bg-night-2 dark:text-dawn"
          />
        </label>
        <Button type="submit" disabled={commit.isPending || path.trim().length === 0}>
          {commit.isPending ? t("pending") : t("submit")}
        </Button>
      </form>
      {commit.isError ? <RequestError code={failureCode(commit.error)}></RequestError> : null}
    </Frame>
  );
}

const linkClass =
  "inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium text-ink underline decoration-accent underline-offset-4 hover:opacity-80 dark:text-dawn";

function Frame({ children }: { children: ReactNode }) {
  const { t } = useTranslation("ingest");
  return (
    <section className="max-w-3xl">
      <h1 className="font-serif text-3xl tracking-tight text-ink dark:text-dawn">{t("title")}</h1>
      <div className="mt-6 space-y-4">{children}</div>
    </section>
  );
}

function RequestError({ code }: { code: string }) {
  const { t } = useTranslation("ingest");
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
