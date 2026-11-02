/**
 * Light, dark, or the device's own setting: chosen on the account menu and kept on this browser,
 * since a phone and a laptop can want different ones. Shown through jigkit's theme module, which
 * colours the browser's bar from app.css's --bg.
 */

import { applyTheme as apply, chooseTheme as choose, chosenTheme as chosen } from "@jmerhar/jigkit/theme";

export type Theme = "auto" | "light" | "dark";

const KEY = "house-cost:theme";

const shown = (theme: Theme) => (theme === "auto" ? null : theme);

/** The theme chosen on this browser, or "auto" to follow the device. */
export function chosenTheme(): Theme {
  return chosen(KEY) ?? "auto";
}

/** Show the page in ``theme``: the stylesheet reads it from <html data-theme>. */
export function applyTheme(theme: Theme): void {
  apply(shown(theme));
}

/** Choose ``theme`` on this browser, and show it. */
export function chooseTheme(theme: Theme): void {
  choose(KEY, shown(theme));
}
