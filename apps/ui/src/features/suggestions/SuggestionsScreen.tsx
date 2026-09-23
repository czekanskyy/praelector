// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import { EmptyScreen } from "../../components/shell/EmptyScreen";

export function SuggestionsScreen() {
  const { t } = useTranslation();
  return <EmptyScreen title={t("suggestions:title")} body={t("suggestions:empty")} />;
}
