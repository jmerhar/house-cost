/**
 * Light, dark, or the device's own setting: chosen on the account menu and kept on this browser,
 * since a phone and a laptop can want different ones.
 */

export type Theme = "auto" | "light" | "dark";

const KEY = "house-cost:theme";
/** The browser bar's colour for each theme, matching the page's background. */
const BAR = { light: "#f7f6f2", dark: "#17191b" } as const;

/** The theme chosen on this browser, or "auto" to follow the device. */
export function chosenTheme(): Theme {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === "light" || stored === "dark" ? stored : "auto";
  } catch {
    return "auto";
  }
}

/** Show the page in ``theme``: the stylesheet reads it from <html data-theme>. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "auto") delete root.dataset.theme;
  else root.dataset.theme = theme;
  // Each theme-color tag answers one device setting; a chosen theme gives both its colour.
  for (const tag of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const own = tag.media.includes("dark") ? BAR.dark : BAR.light;
    tag.content = theme === "auto" ? own : BAR[theme];
  }
}

/** Choose ``theme`` on this browser, and show it. */
export function chooseTheme(theme: Theme): void {
  try {
    if (theme === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // A browser that keeps nothing shows the theme until it is reloaded.
  }
  applyTheme(theme);
}
