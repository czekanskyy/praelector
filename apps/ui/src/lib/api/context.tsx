// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, type ReactNode } from "react";

import type { EngineApi } from "./client";

const EngineApiContext = createContext<EngineApi | null>(null);

export function EngineApiProvider({
  api,
  children,
}: {
  api: EngineApi | null;
  children: ReactNode;
}) {
  return <EngineApiContext.Provider value={api}>{children}</EngineApiContext.Provider>;
}

export function useEngineApi(): EngineApi | null {
  return useContext(EngineApiContext);
}
