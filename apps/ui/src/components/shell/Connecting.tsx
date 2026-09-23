// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

export function Connecting() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6 text-ink dark:bg-night dark:text-dawn">
      <div className="max-w-md">
        <h1 className="font-serif text-3xl">{t("common:connecting_title")}</h1>
        <p className="mt-3 text-ink-soft dark:text-dawn-soft">{t("common:connecting_body")}</p>
      </div>
    </div>
  );
}
