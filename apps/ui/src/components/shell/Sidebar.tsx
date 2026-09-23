// SPDX-License-Identifier: Apache-2.0
import {
  Activity,
  FileInput,
  Library,
  Lightbulb,
  ListTree,
  Mic,
  PenLine,
  Settings,
  Tags,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { ThemeControl } from "./ThemeControl";

const LINKS: readonly { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/library", label: "common:nav_library", icon: Library },
  { to: "/ingest", label: "common:nav_ingest", icon: FileInput },
  { to: "/chapters", label: "common:nav_chapters", icon: ListTree },
  { to: "/editor", label: "common:nav_editor", icon: PenLine },
  { to: "/suggestions", label: "common:nav_suggestions", icon: Lightbulb },
  { to: "/voices", label: "common:nav_voices", icon: Mic },
  { to: "/job", label: "common:nav_job", icon: Activity },
  { to: "/metadata", label: "common:nav_metadata", icon: Tags },
  { to: "/settings", label: "common:nav_settings", icon: Settings },
];

function linkClass(isActive: boolean): string {
  const base = "flex items-center gap-2 rounded-md px-3 py-2 text-sm";
  if (isActive) return `${base} bg-paper text-ink dark:bg-night dark:text-dawn`;
  return `${base} text-ink-soft hover:bg-paper dark:text-dawn-soft dark:hover:bg-night`;
}

export function Sidebar() {
  const { t } = useTranslation();
  return (
    <aside className="flex min-h-screen flex-col border-r border-line bg-paper-2 px-3 py-4 dark:border-night-line dark:bg-night-2">
      <div className="px-3 pb-4 font-serif text-lg text-ink dark:text-dawn">{t("common:app_name")}</div>
      <nav aria-label={t("common:nav_label")} className="flex flex-1 flex-col gap-1">
        {LINKS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => linkClass(isActive)}>
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              <span>{t(item.label)}</span>
            </NavLink>
          );
        })}
      </nav>
      <ThemeControl />
    </aside>
  );
}
