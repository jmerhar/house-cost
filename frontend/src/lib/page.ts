/** The page's name in the person's language, for the tab and for a home screen. */

/**
 * Name the page ``name``: the browser tab's title, and the title iOS gives the app when the page
 * is added to a home screen, which it reads from a meta tag rather than from the manifest.
 */
export function namePage(name: string): void {
  document.title = name;
  document.querySelector('meta[name="apple-mobile-web-app-title"]')?.setAttribute("content", name);
}
