// SPDX-License-Identifier: Apache-2.0
import { z } from "zod";

const copyResult = z.object({
  copied: z.boolean(),
});

/** Invokes the shell command that copies the redacted engine log buffer. */
export async function copyEngineLogs(): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  const parsed = copyResult.safeParse(await invoke("copy_engine_logs"));
  return parsed.success && parsed.data.copied;
}
