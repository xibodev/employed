// TD-001: locale-aware assertion helpers. The default market (mz) serves
// Portuguese; specs must assert against the locale catalog instead of
// hardcoded English copy. Reads the same messages/ files the app ships.
const fs = require('fs');
const path = require('path');

const MESSAGES_DIR = path.resolve(__dirname, '..', '..', 'frontend', 'messages');
const DEFAULT_LOCALE = process.env.E2E_LOCALE || 'pt';
const LOCALES = ['en', 'pt', 'es'];

const cache = new Map();

function loadMessages(locale) {
  if (!cache.has(locale)) {
    cache.set(locale, JSON.parse(fs.readFileSync(path.join(MESSAGES_DIR, `${locale}.json`), 'utf-8')));
  }
  return cache.get(locale);
}

function lookup(messages, key) {
  return key.split('.').reduce((acc, part) => (acc == null ? acc : acc[part]), messages);
}

/** Translated string for `key` ("namespace.key") in `locale` (default pt). */
function t(key, locale = DEFAULT_LOCALE) {
  const value = lookup(loadMessages(locale), key);
  if (typeof value !== 'string') {
    throw new Error(`i18n key not found: ${key} (${locale})`);
  }
  return value;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Case-insensitive RegExp matching the key's copy in ANY locale. */
function anyLocaleRegex(key) {
  const variants = LOCALES.map((locale) => lookup(loadMessages(locale), key))
    .filter((value) => typeof value === 'string')
    .map(escapeRegExp);
  if (variants.length === 0) {
    throw new Error(`i18n key not found in any locale: ${key}`);
  }
  return new RegExp([...new Set(variants)].join('|'), 'i');
}

module.exports = { t, anyLocaleRegex, loadMessages, DEFAULT_LOCALE };
