// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function ChaptersScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("chapters:title")} body={t("chapters:empty")} />;
}
