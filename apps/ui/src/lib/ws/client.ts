// SPDX-License-Identifier: Apache-2.0
import { getEngineEndpoint } from "../api/client";

export interface WsEvent<T = unknown> {
  seq: number;
  event: string;
  data: T;
}

export type WsEventHandler = (event: WsEvent) => void;

export class EngineWsClient {
  private ws: WebSocket | null = null;
  private lastSeq = 0;
  private handlers = new Set<WsEventHandler>();
  private reconnectTimer: number | null = null;
  private shouldReconnect = true;

  constructor() {}

  connect(): void {
    this.shouldReconnect = true;
    const { baseUrl, token } = getEngineEndpoint();
    const wsUrl = baseUrl.replace(/^http/, "ws") + `/ws?token=${encodeURIComponent(token)}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as WsEvent;
          if (typeof parsed.seq === "number") {
            this.lastSeq = Math.max(this.lastSeq, parsed.seq);
          }
          for (const handler of this.handlers) {
            handler(parsed);
          }
        } catch (e) {
          console.error("Failed to parse WS event", e);
        }
      };

      this.ws.onclose = () => {
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (err) => {
        console.warn("WS error", err);
        this.ws?.close();
      };
    } catch (e) {
      console.error("Error creating WebSocket", e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) {
        this.connect();
      }
    }, 2000);
  }

  subscribe(handler: WsEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  getLastSeq(): number {
    return this.lastSeq;
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export const wsClient = new EngineWsClient();
