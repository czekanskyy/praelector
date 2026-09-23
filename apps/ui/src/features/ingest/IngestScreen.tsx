// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function IngestScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("ingest:title")} body={t("ingest:empty")} />;
}
