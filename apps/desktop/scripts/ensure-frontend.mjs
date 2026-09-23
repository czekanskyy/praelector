// SPDX-License-Identifier: Apache-2.0
// `tauri build` runs this before the Rust compile. The UI package lands in a
// later PR; until then a one-file dist is enough for the shell to link.

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../..");
const uiPackage = resolve(repo, "apps/ui/package.json");
const index = resolve(repo, "apps/ui/dist/index.html");

if (existsSync(uiPackage)) {
  // spawnSync cannot run a `.cmd` shim without a shell: Node reports EINVAL.
  const result = spawnSync("pnpm", ["-F", "ui", "build"], {
    cwd: repo,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

mkdirSync(dirname(index), { recursive: true });
writeFileSync(
  index,
  "<!doctype html><html><head><meta charset=\"utf-8\"><title>Praelector</title></head><body></body></html>\n",
);
