// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { translateError } from "../../lib/errors";
import { copyEngineLogs } from "../../lib/tauri/commands";
import { inTauriWebview } from "../../lib/tauri/runtime";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";

export function FatalPanel({ code }: { code: string | null }) {
  const { t } = useTranslation();
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    setCopyState("idle");
  }, [code]);

  if (!inTauriWebview() || code === null) return null;

  const message = translateError(
    (key, options) => t(key, options),
    code,
  );

  return (
    <Dialog title={t("common:fatal_title")} titleId="engine-fatal-title">
      <p>{t("common:fatal_code")}</p>
      <code className="block font-mono text-sm text-ink dark:text-dawn">{code}</code>
      <p>{message}</p>
      <Button
        onClick={() => {
          void copyEngineLogs()
            .then((copied) => setCopyState(copied ? "copied" : "failed"))
            .catch(() => setCopyState("failed"));
        }}
      >
        {t("common:copy_logs")}
      </Button>
      {copyState === "copied" ? <p>{t("common:copy_logs_done")}</p> : null}
      {copyState === "failed" ? <p>{t("common:copy_logs_failed")}</p> : null}
    </Dialog>
  );
}
