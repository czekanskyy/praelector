// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";

interface ProjectStoreState {
  activeProjectId: string | null;
  activeChapterId: string | null;
  isIngestModalOpen: boolean;
  setActiveProjectId: (id: string | null) => void;
  setActiveChapterId: (id: string | null) => void;
  setIsIngestModalOpen: (open: boolean) => void;
}

export const useProjectStore = create<ProjectStoreState>((set) => ({
  activeProjectId: null,
  activeChapterId: null,
  isIngestModalOpen: false,
  setActiveProjectId: (id) => set({ activeProjectId: id, activeChapterId: null }),
  setActiveChapterId: (id) => set({ activeChapterId: id }),
  setIsIngestModalOpen: (open) => set({ isIngestModalOpen: open }),
}));
