// SPDX-License-Identifier: Apache-2.0
/**
 * Catalogue parity, dead-key and hardcoded-literal checks (IX-01 / IX-02).
 *
 * CI_AND_RELEASE.md §3 names `i18next-parser` for the literal scan. This file
 * deliberately implements all three checks with zero dependencies so the CI job
 * can never fail because a parser package drifted, and so the heuristics are
 * reviewable in one place. Recorded deviation, not an oversight.
 *
 * exit codes: 0 clean (or nothing to check yet), 1 policy failure, 2 usage error
 */

import { readdirSync, readFileSync, existsSync, statSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_ROOT = path.resolve(SCRIPT_DIR, "..");

const SOURCE_NS = "en";
const TARGET_NS = "pl";
const LOCALES_RELPATH = path.join("apps", "ui", "src", "i18n", "locales");
const SRC_RELPATH = path.join("apps", "ui", "src");
const IGNORE_UNUSED_RELPATH = path.join(
  "apps",
  "ui",
  "src",
  "i18n",
  "ignore-unused.json",
);
const DISPLAY_PROPS = ["title", "label", "placeholder", "alt", "aria-label"];

// Report paths the way the repository writes them, so CI logs on Windows and on
// ubuntu-latest look identical.
const show = (value) => value.split(path.sep).join("/");

const HELP = `usage: node scripts/i18n_check.mjs [--root DIR] [--allow-unused GLOB]...

Checks the en/pl catalogues under apps/ui/src/i18n/locales:
  1. parity      every en key exists in pl and vice versa (IX-01)
  2. values      no key holds an empty or whitespace-only string
  3. usage       every key is referenced somewhere in apps/ui/src (dead strings rot)
  4. literals    no JSX text node or display prop carries an untranslated string (IX-02)

options:
  --root DIR            repository root (default: the parent of scripts/)
  --allow-unused GLOB   exempt keys from the usage check; matches "ns" or
                        "ns:dotted.key", repeatable
  -h, --help            this message

exit codes: 0 clean, 1 problems found, 2 usage or unreadable input
`;

function fail(message) {
  process.stderr.write(`error: ${message}\n`);
  process.exit(2);
}

function parseArgs(argv) {
  const options = { root: DEFAULT_ROOT, allowUnused: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") {
      process.stdout.write(HELP);
      process.exit(0);
    } else if (arg === "--root") {
      i += 1;
      if (i >= argv.length) fail("--root needs a value");
      options.root = path.resolve(argv[i]);
    } else if (arg.startsWith("--root=")) {
      options.root = path.resolve(arg.slice("--root=".length));
    } else if (arg === "--allow-unused") {
      i += 1;
      if (i >= argv.length) fail("--allow-unused needs a value");
      options.allowUnused.push(argv[i]);
    } else if (arg.startsWith("--allow-unused=")) {
      options.allowUnused.push(arg.slice("--allow-unused=".length));
    } else {
      fail(`unknown argument ${arg} (see --help)`);
    }
  }
  return options;
}

function walk(dir, extensions, out = []) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "locales") continue;
      walk(full, extensions, out);
    } else if (extensions.includes(path.extname(entry.name))) {
      // Component tests legitimately assert on literal strings; they never render
      // to a user.
      if (/\.test\.[cm]?[jt]sx?$/.test(entry.name)) continue;
      if (/\.spec\.[cm]?[jt]sx?$/.test(entry.name)) continue;
      out.push(full);
    }
  }
  return out;
}

function readJson(file) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch (error) {
    fail(`cannot read ${file}: ${error.message}`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    fail(`${file} is not valid JSON: ${error.message}`);
  }
}

function flatten(node, prefix, out) {
  for (const [key, value] of Object.entries(node)) {
    const dotted = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      flatten(value, dotted, out);
    } else {
      out.set(dotted, value);
    }
  }
  return out;
}

function globToRegExp(glob) {
  const escaped = glob
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "\u0000")
    .replace(/\*/g, "[^:]*")
    .replace(/\u0000/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`);
}

function loadCatalogues(localesDir) {
  const table = new Map();
  for (const locale of [SOURCE_NS, TARGET_NS]) {
    const dir = path.join(localesDir, locale);
    if (!existsSync(dir) || !statSync(dir).isDirectory()) {
      table.set(locale, new Map());
      continue;
    }
    const namespaces = new Map();
    for (const file of readdirSync(dir).filter((n) => n.endsWith(".json")).sort()) {
      const namespace = file.slice(0, -".json".length);
      namespaces.set(namespace, flatten(readJson(path.join(dir, file)), "", new Map()));
    }
    table.set(locale, namespaces);
  }
  return table;
}

function quotedLiterals(source) {
  const found = new Set();
  const patterns = [
    /'((?:[^'\\\n]|\\.)*)'/g,
    /"((?:[^"\\\n]|\\.)*)"/g,
    /`([^`]*)`/g,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      found.add(match[1]);
    }
  }
  return found;
}

function collectUsage(srcDir) {
  const literals = new Set();
  const bareByFile = new Map();
  const defaultNsByFile = new Map();
  const dynamicNamespaces = new Set();

  const callPattern =
    /(?:^|[^\w$.])(?:i18n\s*\.\s*)?t\s*\(\s*(['"`])([^'"`]*?)\1/gs;
  const hookPatterns = [
    /(?:useTranslation|withTranslation)\s*\(\s*(?:\[\s*)?(['"`])([^'"`]+)\1/g,
    /(?:useTranslation|withTranslation)\s*\(\s*\[([^\]]*)\]/g,
    /defaultNS\s*:\s*(['"`])([^'"`]+)\1/g,
  ];

  for (const file of walk(srcDir, [".ts", ".tsx", ".mts", ".cts"])) {
    const source = readFileSync(file, "utf8");
    const bare = new Set();
    const namespaces = new Set();

    for (const literal of quotedLiterals(source)) {
      literals.add(literal);
      // `t(\`errors:${code}\`)` cannot be resolved statically; exempting the whole
      // namespace beats reporting dozens of false dead keys (D-16 maps error codes
      // to catalogue keys at runtime).
      const dynamic = /^([\w-]+)[:.]\$\{/.exec(literal);
      if (dynamic) dynamicNamespaces.add(dynamic[1]);
    }

    for (const match of source.matchAll(callPattern)) {
      const key = match[2];
      if (!key.includes(":")) bare.add(key);
    }
    for (const pattern of hookPatterns) {
      for (const match of source.matchAll(pattern)) {
        const value = match[2] ?? match[1];
        for (const literal of quotedLiterals(value)) namespaces.add(literal);
        if (match[2]) namespaces.add(match[2]);
      }
    }

    bareByFile.set(file, bare);
    defaultNsByFile.set(file, namespaces);
  }

  return { literals, bareByFile, defaultNsByFile, dynamicNamespaces };
}

function loadIgnoreList(root) {
  const file = path.join(root, IGNORE_UNUSED_RELPATH);
  if (!existsSync(file)) return new Set();
  const data = readJson(file);
  const keys = new Set();
  const entries = Array.isArray(data) ? data : data.keys;
  if (!Array.isArray(entries)) {
    process.stderr.write(
      `warning: ${show(IGNORE_UNUSED_RELPATH)} is neither an array nor {"keys": [...]}; ignored\n`,
    );
    return keys;
  }
  for (const entry of entries) {
    if (typeof entry === "string") keys.add(entry);
    else if (entry && typeof entry.key === "string") keys.add(entry.key);
    else
      process.stderr.write(
        `warning: ${show(IGNORE_UNUSED_RELPATH)} has an entry this script does not understand: ${JSON.stringify(entry)}\n`,
      );
  }
  return keys;
}

function lineNumber(source, index) {
  let line = 1;
  for (let i = 0; i < index && i < source.length; i += 1) {
    if (source[i] === "\n") line += 1;
  }
  return line;
}

// Comments are detected positionally rather than stripped so that reported line
// numbers still point at the real source. Crude on purpose: it can only ever
// suppress a finding, never invent one.
function isCommented(source, index) {
  const lineStart = source.lastIndexOf("\n", index) + 1;
  const prefix = source.slice(lineStart, index);
  const slashes = prefix.indexOf("//");
  if (slashes !== -1) {
    const before = prefix.slice(0, slashes);
    const quotes = (before.match(/['"`]/g) ?? []).length;
    if (quotes % 2 === 0) return true;
  }
  const head = source.slice(0, index);
  const opens = (head.match(/\/\*/g) ?? []).length;
  const closes = (head.match(/\*\//g) ?? []).length;
  return opens > closes;
}

function isClassList(value) {
  const tokens = value.trim().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return false;
  const classish = /^[a-z][a-z0-9]*(?:[-:./][a-z0-9%[\](),#_.-]*)*$/;
  if (!tokens.every((token) => classish.test(token))) return false;
  // A tailwind list needs at least one modifier; without this, an all-lowercase
  // English sentence ("the quick brown fox") would be excused.
  return tokens.some((token) => /[-:/.[\]]/.test(token));
}

function looksLikeUiText(raw) {
  const value = raw.replace(/\s+/g, " ").trim();
  if (!value) return false;
  if (!/[A-Za-z\u00c0-\u024f]/.test(value)) return false;
  if (/^(&[a-zA-Z#0-9]+;|\s)+$/.test(value)) return false;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value) || /^(https?|mailto|file|data|blob):/i.test(value))
    return false;
  if (/^[./#?]/.test(value)) return false;
  if (/^[A-Za-z_$][\w$]*(?:[.:\-][A-Za-z_$][\w$-]*)*$/.test(value) && !/\s/.test(value))
    return false;
  if (/^[A-Z0-9_\-:. ]+$/.test(value)) return false;
  if (isClassList(value)) return false;
  return true;
}

function findTagClose(source, from) {
  let depth = 0;
  let quote = null;
  for (let i = from; i < source.length; i += 1) {
    const char = source[i];
    if (quote !== null) {
      if (char === "\\") i += 1;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      continue;
    }
    if (char === "{") depth += 1;
    else if (char === "}") depth -= 1;
    else if (char === ">" && depth <= 0) return i;
  }
  return -1;
}

function stripExpressionContainers(text) {
  let out = "";
  let depth = 0;
  for (const char of text) {
    if (char === "{") {
      depth += 1;
      continue;
    }
    if (char === "}") {
      if (depth > 0) depth -= 1;
      continue;
    }
    if (depth === 0) out += char;
  }
  return out;
}

function jsxTagSpans(source) {
  const spans = [];
  for (const match of source.matchAll(/<[A-Za-z][\w.$-]*/g)) {
    const index = match.index;
    const previous = index > 0 ? source[index - 1] : "";
    // `Array<string>` and `Foo<T>` are generics: a `<` glued to an identifier is a
    // type argument list, never a JSX element.
    if (/[\w$.]/.test(previous)) continue;
    if (isCommented(source, index)) continue;
    const close = findTagClose(source, index + match[0].length);
    if (close === -1) continue;
    spans.push({ open: index, close });
  }
  return spans;
}

function insideTag(spans, index) {
  return spans.some((span) => index > span.open && index < span.close);
}

function hardcodedLiterals(srcDir, rel) {
  const findings = [];
  const propPattern = new RegExp(
    `(?<![\\w$-])(${DISPLAY_PROPS.join("|")})\\s*=\\s*(?:"([^"]*)"|'([^']*)'|\\{\\s*(["'])((?:\\\\.|(?!\\4).)*)\\4\\s*\\})`,
    "g",
  );

  for (const file of walk(srcDir, [".tsx"])) {
    const source = readFileSync(file, "utf8");
    const spans = jsxTagSpans(source);

    for (const match of source.matchAll(propPattern)) {
      const index = match.index;
      // `const label = "..."` is a variable, not a JSX attribute; only report
      // matches that sit inside a tag's attribute list.
      if (!insideTag(spans, index)) continue;
      const value = match[2] ?? match[3] ?? match[5] ?? "";
      if (!looksLikeUiText(value)) continue;
      findings.push({
        file: rel(file),
        line: lineNumber(source, index),
        prop: match[1],
        text: value,
      });
    }

    for (const span of spans) {
      const nextTag = source.indexOf("<", span.close + 1);
      if (nextTag === -1) continue;
      const text = stripExpressionContainers(source.slice(span.close + 1, nextTag));
      if (!looksLikeUiText(text)) continue;
      findings.push({
        file: rel(file),
        line: lineNumber(source, span.close + 1),
        prop: "jsx text",
        text: text.replace(/\s+/g, " ").trim(),
      });
    }
  }
  // Two passes (attributes, then text runs) produce out-of-order hits.
  return findings.sort(
    (a, b) => a.file.localeCompare(b.file) || a.line - b.line || a.prop.localeCompare(b.prop),
  );
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const root = options.root;
  if (!existsSync(root) || !statSync(root).isDirectory()) {
    fail(`--root is not a directory: ${root}`);
  }

  const localesDir = path.join(root, LOCALES_RELPATH);
  if (!existsSync(localesDir)) {
    process.stdout.write(
      [
        `SKIP  ${show(LOCALES_RELPATH)} does not exist yet.`,
        "",
        "      The UI tree lands in a later PR of this stacked series, so there is",
        "      nothing to compare. NO CHECK RAN — this is not a pass, it is a skip,",
        "      and the parity/usage/literal checks switch on automatically the moment",
        "      apps/ui/src/i18n/locales is added.",
        "",
      ].join("\n"),
    );
    return 0;
  }

  const rel = (file) => path.relative(root, file).split(path.sep).join("/");
  const srcDir = path.join(root, SRC_RELPATH);
  const catalogues = loadCatalogues(localesDir);
  const source = catalogues.get(SOURCE_NS);
  const target = catalogues.get(TARGET_NS);

  const problems = {
    parity: [],
    empty: [],
    unused: [],
    literal: [],
  };

  const namespaces = [...new Set([...source.keys(), ...target.keys()])].sort();
  for (const namespace of namespaces) {
    const en = source.get(namespace) ?? new Map();
    const pl = target.get(namespace) ?? new Map();
    for (const key of [...en.keys()].sort()) {
      if (!pl.has(key)) problems.parity.push({ namespace, key, missing: TARGET_NS });
    }
    for (const key of [...pl.keys()].sort()) {
      if (!en.has(key)) problems.parity.push({ namespace, key, missing: SOURCE_NS });
    }
    for (const [locale, table] of [
      [SOURCE_NS, en],
      [TARGET_NS, pl],
    ]) {
      for (const [key, value] of [...table.entries()].sort()) {
        if (typeof value === "string" && value.trim() === "") {
          problems.empty.push({ namespace, key, locale });
        }
      }
    }
  }

  const usage = existsSync(srcDir) ? collectUsage(srcDir) : null;
  const ignored = loadIgnoreList(root);
  const allowUnused = options.allowUnused.map(globToRegExp);

  if (usage) {
    const bareUsed = new Set();
    for (const [file, bare] of usage.bareByFile) {
      const namespacesOfFile = usage.defaultNsByFile.get(file) ?? new Set();
      for (const namespace of namespacesOfFile) {
        for (const key of bare) bareUsed.add(`${namespace}:${key}`);
      }
    }

    for (const namespace of namespaces) {
      const table = source.get(namespace) ?? new Map();
      for (const key of [...table.keys()].sort()) {
        const qualified = `${namespace}:${key}`;
        if (usage.dynamicNamespaces.has(namespace)) continue;
        if (usage.literals.has(qualified)) continue;
        if (bareUsed.has(qualified)) continue;
        if (ignored.has(qualified) || ignored.has(key)) continue;
        if (allowUnused.some((pattern) => pattern.test(qualified) || pattern.test(namespace)))
          continue;
        problems.unused.push({ namespace, key });
      }
    }

    problems.literal = hardcodedLiterals(srcDir, rel);
  } else {
    process.stderr.write(
      `warning: ${show(SRC_RELPATH)} does not exist; usage and literal checks were skipped\n`,
    );
  }

  const keyCount = (table) =>
    [...table.values()].reduce((total, flat) => total + flat.size, 0);
  process.stdout.write(
    `i18n: ${namespaces.length} namespace(s), ${keyCount(source)} ${SOURCE_NS} key(s), ` +
      `${keyCount(target)} ${TARGET_NS} key(s)\n`,
  );

  if (problems.parity.length) {
    process.stdout.write(`\nIX-01 parity (${problems.parity.length})\n`);
    for (const item of problems.parity) {
      process.stdout.write(
        `  missing in ${item.missing}: ${item.namespace}:${item.key}\n`,
      );
    }
  }
  if (problems.empty.length) {
    process.stdout.write(`\nIX-01 empty value (${problems.empty.length})\n`);
    for (const item of problems.empty) {
      process.stdout.write(`  ${item.namespace}:${item.key} is empty in ${item.locale}\n`);
    }
  }
  if (problems.unused.length) {
    process.stdout.write(`\nIX-01 unused key (${problems.unused.length})\n`);
    for (const item of problems.unused) {
      process.stdout.write(
        `  ${item.namespace}:${item.key} is not referenced in ${show(SRC_RELPATH)}\n`,
      );
    }
    process.stdout.write(
      `  exempt deliberately dynamic keys via ${show(IGNORE_UNUSED_RELPATH)}\n` +
        "  or --allow-unused <glob>\n",
    );
  }
  if (problems.literal.length) {
    process.stdout.write(`\nIX-02 hardcoded literal (${problems.literal.length})\n`);
    for (const item of problems.literal) {
      process.stdout.write(
        `  ${item.file}:${item.line} — ${item.prop}=${JSON.stringify(item.text)}\n`,
      );
    }
  }

  const total =
    problems.parity.length +
    problems.empty.length +
    problems.unused.length +
    problems.literal.length;
  if (total > 0) {
    process.stderr.write(
      `\nFAIL: ${total} problem(s) — parity ${problems.parity.length}, ` +
        `empty ${problems.empty.length}, unused ${problems.unused.length}, ` +
        `hardcoded ${problems.literal.length}\n`,
    );
    return 1;
  }

  process.stdout.write(
    `ok: en/pl catalogues match, every key is used, no hardcoded literals\n`,
  );
  return 0;
}

process.exit(main());
