// SPDX-License-Identifier: Apache-2.0

/** Loopback coordinates. The shell command may hand back a port or a base URL. */
export interface EngineCoordinates {
  port: number;
  token: string;
}

/** One replayed or live event envelope. `seq` is monotonic for the process. */
export interface SeqFrame {
  seq: number;
  type: string;
  payload?: unknown;
}
