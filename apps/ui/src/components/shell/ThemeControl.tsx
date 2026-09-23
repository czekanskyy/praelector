// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";

import type { ThemeChoice } from "../../lib/theme/theme";
import { Button } from "../ui/button";
import { useThemeChoice } from "./ThemeRoot";

const OPTIONS: readonly { choice: ThemeChoice; label: string }[] = [
  { choice: "system", label: "common:theme_system" },
  { choice: "light", label: "common:theme_light" },
  { choice: "dark", label: "common:theme_dark" },
];

export function ThemeControl() {
  const { t } = useTranslation();
  const { choice, setChoice } = useThemeChoice();
  return (
    <div
      role="group"
      aria-label={t("common:theme_label")}
      className="mt-4 border-t border-line pt-3 dark:border-night-line"
    >
      <div className="grid grid-cols-3 gap-1">
        {OPTIONS.map((option) => (
          <Button
            key={option.choice}
            variant="quiet"
            aria-pressed={choice === option.choice}
            className={`px-1 py-1 text-xs ${choice === option.choice ? "bg-paper dark:bg-night" : ""}`}
            onClick={() => setChoice(option.choice)}
          >
            {t(option.label)}
          </Button>
        ))}
      </div>
    </div>
  );
}
