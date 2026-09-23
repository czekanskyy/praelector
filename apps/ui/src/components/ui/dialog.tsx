// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";

export function Dialog({
  title,
  titleId,
  children,
}: {
  title: string;
  titleId: string;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 dark:bg-black/60">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-lg border border-line bg-paper p-6 text-ink shadow-lg dark:border-night-line dark:bg-night-2 dark:text-dawn"
      >
        <h2 id={titleId} className="font-serif text-xl">
          {title}
        </h2>
        <div className="mt-4 space-y-3 text-sm text-ink-soft dark:text-dawn-soft">{children}</div>
      </div>
    </div>
  );
}
