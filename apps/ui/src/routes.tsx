// SPDX-License-Identifier: Apache-2.0
import { Navigate, Route, Routes } from "react-router";

import { Shell } from "./components/shell/Shell";
import { ChaptersScreen } from "./features/chapters/ChaptersScreen";
import { EditorScreen } from "./features/editor/EditorScreen";
import { IngestScreen } from "./features/ingest/IngestScreen";
import { JobScreen } from "./features/job/JobScreen";
import { LibraryScreen } from "./features/library/LibraryScreen";
import { MetadataScreen } from "./features/metadata/MetadataScreen";
import { SettingsScreen } from "./features/settings/SettingsScreen";
import { SuggestionsScreen } from "./features/suggestions/SuggestionsScreen";
import { VoicesScreen } from "./features/voices/VoicesScreen";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/library" replace />} />
        <Route path="library" element={<LibraryScreen />} />
        <Route path="ingest" element={<IngestScreen />} />
        <Route path="chapters" element={<ChaptersScreen />} />
        <Route path="editor" element={<EditorScreen />} />
        <Route path="suggestions" element={<SuggestionsScreen />} />
        <Route path="voices" element={<VoicesScreen />} />
        <Route path="job" element={<JobScreen />} />
        <Route path="metadata" element={<MetadataScreen />} />
        <Route path="settings" element={<SettingsScreen />} />
        <Route path="*" element={<Navigate to="/library" replace />} />
      </Route>
    </Routes>
  );
}
