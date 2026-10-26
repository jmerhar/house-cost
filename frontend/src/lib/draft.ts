/**
 * A bill read from a file, handed from the bills list to the bill form that checks it. Held in
 * memory only: a reload drops it, and the file is read again.
 */

import type { Proposal } from "./api";

export type Draft = { proposal: Proposal; file: File };

let pending: Draft | null = null;

/** Keep a read bill for the bill form to open with. */
export function holdDraft(draft: Draft): void {
  pending = draft;
}

/** The read bill waiting for the bill form, if any; it is handed over once. */
export function takeDraft(): Draft | null {
  const draft = pending;
  pending = null;
  return draft;
}
