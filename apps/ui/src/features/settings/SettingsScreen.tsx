// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function SettingsScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("settings:title")} body={t("settings:empty")} />;
}
