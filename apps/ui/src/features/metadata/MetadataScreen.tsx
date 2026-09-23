// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function MetadataScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("metadata:title")} body={t("metadata:empty")} />;
}
