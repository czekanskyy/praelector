// SPDX-License-Identifier: Apache-2.0

/**
 * `since` for `GET /v1/events` when `seq` skips ahead of the last contiguous
 * value. Duplicates and the next expected number are not gaps.
 */
export function gapSince(last: number, seq: number): number | null {
  if (!Number.isInteger(seq) || !Number.isInteger(last)) return null;
  if (seq <= last + 1) return null;
  return last;
}
