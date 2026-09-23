// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function LibraryScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("library:title")} body={t("library:empty")} />;
}
