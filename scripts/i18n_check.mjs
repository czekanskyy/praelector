// SPDX-License-Identifier: Apache-2.0
/**
 * Verifies key parity between en and pl localization catalogues.
 */

import fs from 'node:fs';
import path from 'node:path';

const localesDir = path.resolve('apps/ui/src/i18n/locales');

function getKeys(obj, prefix = '') {
  return Object.keys(obj).reduce((res, el) => {
    if (Array.isArray(obj[el])) {
      return res;
    }
    if (typeof obj[el] === 'object' && obj[el] !== null) {
      return [...res, ...getKeys(obj[el], prefix + el + '.')];
    }
    return [...res, prefix + el];
  }, []);
}

function checkParity() {
  const enDir = path.join(localesDir, 'en');
  const plDir = path.join(localesDir, 'pl');

  if (!fs.existsSync(enDir) || !fs.existsSync(plDir)) {
    console.log('Localization catalogues not yet initialized. Skipping parity check.');
    return 0;
  }

  const enFiles = fs.readdirSync(enDir).filter(f => f.endsWith('.json'));
  const plFiles = fs.readdirSync(plDir).filter(f => f.endsWith('.json'));

  let hasError = false;

  for (const file of enFiles) {
    if (!plFiles.includes(file)) {
      console.error(`Missing Polish catalogue file: pl/${file}`);
      hasError = true;
      continue;
    }

    const enContent = JSON.parse(fs.readFileSync(path.join(enDir, file), 'utf-8'));
    const plContent = JSON.parse(fs.readFileSync(path.join(plDir, file), 'utf-8'));

    const enKeys = new Set(getKeys(enContent));
    const plKeys = new Set(getKeys(plContent));

    for (const key of enKeys) {
      if (!plKeys.has(key)) {
        console.error(`Key "${key}" in en/${file} missing from pl/${file}`);
        hasError = true;
      }
    }

    for (const key of plKeys) {
      if (!enKeys.has(key)) {
        console.error(`Key "${key}" in pl/${file} missing from en/${file}`);
        hasError = true;
      }
    }
  }

  for (const file of plFiles) {
    if (!enFiles.includes(file)) {
      console.error(`Missing English catalogue file: en/${file}`);
      hasError = true;
    }
  }

  if (hasError) {
    console.error('i18n parity check failed.');
    return 1;
  }

  console.log('i18n parity check passed: 100% key parity between en and pl.');
  return 0;
}

process.exit(checkParity());
