// SPDX-License-Identifier: Apache-2.0
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "quiet";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-fg hover:opacity-90 dark:bg-ember dark:text-ember-fg",
  quiet: "bg-transparent text-ink hover:bg-paper dark:text-dawn dark:hover:bg-night",
};

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 ${VARIANT[variant]} ${className}`}
      {...props}
    />
  );
}
