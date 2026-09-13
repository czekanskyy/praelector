// SPDX-License-Identifier: Apache-2.0
import React from "react";
import { BookOpen, CheckSquare, Cog, FileText, Mic, PlaySquare, Share2 } from "lucide-react";

export type NavTab =
  | "library"
  | "editor"
  | "suggestions"
  | "voices"
  | "job"
  | "export"
  | "settings";

export interface NavItem {
  id: NavTab;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "library", labelKey: "library:title", icon: BookOpen },
  { id: "editor", labelKey: "editor:title", icon: FileText },
  { id: "suggestions", labelKey: "suggestions:title", icon: CheckSquare },
  { id: "voices", labelKey: "voices:title", icon: Mic },
  { id: "job", labelKey: "job:title", icon: PlaySquare },
  { id: "export", labelKey: "metadata:title", icon: Share2 },
  { id: "settings", labelKey: "settings:title", icon: Cog },
];
