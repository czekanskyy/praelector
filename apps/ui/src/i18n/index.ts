// SPDX-License-Identifier: Apache-2.0
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// English
import enChapters from "./locales/en/chapters.json";
import enCommon from "./locales/en/common.json";
import enEditor from "./locales/en/editor.json";
import enErrors from "./locales/en/errors.json";
import enIngest from "./locales/en/ingest.json";
import enJob from "./locales/en/job.json";
import enLibrary from "./locales/en/library.json";
import enMetadata from "./locales/en/metadata.json";
import enSettings from "./locales/en/settings.json";
import enSuggestions from "./locales/en/suggestions.json";
import enVoices from "./locales/en/voices.json";

// Polish
import plChapters from "./locales/pl/chapters.json";
import plCommon from "./locales/pl/common.json";
import plEditor from "./locales/pl/editor.json";
import plErrors from "./locales/pl/errors.json";
import plIngest from "./locales/pl/ingest.json";
import plJob from "./locales/pl/job.json";
import plLibrary from "./locales/pl/library.json";
import plMetadata from "./locales/pl/metadata.json";
import plSettings from "./locales/pl/settings.json";
import plSuggestions from "./locales/pl/suggestions.json";
import plVoices from "./locales/pl/voices.json";

export const resources = {
  en: {
    common: enCommon,
    library: enLibrary,
    ingest: enIngest,
    chapters: enChapters,
    editor: enEditor,
    suggestions: enSuggestions,
    voices: enVoices,
    job: enJob,
    metadata: enMetadata,
    settings: enSettings,
    errors: enErrors,
  },
  pl: {
    common: plCommon,
    library: plLibrary,
    ingest: plIngest,
    chapters: plChapters,
    editor: plEditor,
    suggestions: plSuggestions,
    voices: plVoices,
    job: plJob,
    metadata: plMetadata,
    settings: plSettings,
    errors: plErrors,
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
