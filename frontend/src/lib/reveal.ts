/** Bringing a form that just opened into view, for people who opened it far down a list. */

import { tick } from "svelte";

/**
 * Once the page has updated, scroll the element ``selector`` names into view and put the cursor
 * in its first field. Edit forms open at the top of a page, out of sight on a phone when the
 * row that opened them is further down.
 */
export async function reveal(selector: string): Promise<void> {
  await tick();
  const target = document.querySelector<HTMLElement>(selector);
  if (!target) return;
  target.scrollIntoView?.({ block: "start", behavior: "smooth" });
  target.querySelector<HTMLElement>("input, select, textarea")?.focus({ preventScroll: true });
}
