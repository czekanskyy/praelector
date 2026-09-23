// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import { z } from "zod";

import { Connecting } from "./components/shell/Connecting";
import { FatalPanel } from "./components/shell/FatalPanel";
import { ThemeRoot } from "./components/shell/ThemeRoot";
import { EngineApi } from "./lib/api/client";
import { failureCode, loadEngineEndpoint } from "./lib/api/endpoint";
import { inTauriWebview } from "./lib/tauri/runtime";
import { EngineEvents } from "./lib/ws/client";
import { AppRoutes } from "./routes";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: false },
  },
});

const statePayload = z.object({
  state: z.string(),
  error: z.object({ code: z.string().min(1) }).nullish(),
});

const failurePayload = z.object({
  code: z.string().min(1),
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeRoot>
        <BrowserRouter>
          <ConnectionGate />
        </BrowserRouter>
      </ThemeRoot>
    </QueryClientProvider>
  );
}

function ConnectionGate() {
  const inShell = inTauriWebview();
  const endpoint = useQuery({
    queryKey: ["engine", "endpoint"],
    queryFn: loadEngineEndpoint,
    enabled: inShell,
    staleTime: Infinity,
    retry: (failureCount, error) => failureCode(error) === "engine.not_ready" && failureCount < 8,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4000),
  });
  const [eventCode, setEventCode] = useState<string | null>(null);
  const port = endpoint.data?.port;
  const token = endpoint.data?.token;
  const refetchEndpoint = endpoint.refetch;

  useEffect(() => {
    if (port === undefined || token === undefined) return;
    const coords = { port, token };
    const events = new EngineEvents(coords, new EngineApi(coords));
    events.connect();
    return () => events.close();
  }, [port, token]);

  useEffect(() => {
    if (!inShell) return;
    const stops: Array<() => void> = [];
    let cancelled = false;

    void (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      if (cancelled) return;
      const stopState = await listen("engine://state", (event) => {
        const parsed = statePayload.safeParse(event.payload);
        if (!parsed.success) return;
        if (parsed.data.state === "ready") {
          setEventCode(null);
          void refetchEndpoint();
          return;
        }
        if (parsed.data.state === "fatal" && parsed.data.error) {
          setEventCode(parsed.data.error.code);
        }
      });
      if (cancelled) {
        stopState();
        return;
      }
      stops.push(stopState);
      const stopFailure = await listen("engine://failure", (event) => {
        const parsed = failurePayload.safeParse(event.payload);
        if (parsed.success) setEventCode(parsed.data.code);
      });
      if (cancelled) {
        stopFailure();
        return;
      }
      stops.push(stopFailure);
    })();

    return () => {
      cancelled = true;
      for (const stop of stops.splice(0)) stop();
    };
  }, [inShell, refetchEndpoint]);

  const code = eventCode ?? (endpoint.isError ? failureCode(endpoint.error) : null);
  const blocked = inShell && !endpoint.isSuccess;

  return (
    <>
      {blocked ? <Connecting /> : <AppRoutes />}
      <FatalPanel code={inShell ? code : null} />
    </>
  );
}
