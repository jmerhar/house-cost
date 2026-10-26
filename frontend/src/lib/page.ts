/** The page's name in the person's language, for the tab and for a home screen. */

/**
 * Name the page ``name``: the browser tab's title, the title iOS gives the app when the page is
 * added to a home screen (from a meta tag), and the manifest's address, which carries the name so
 * that a renamed app is a new address the browser fetches afresh.
 */
export function namePage(name: string): void {
  document.title = name;
  document.querySelector('meta[name="apple-mobile-web-app-title"]')?.setAttribute("content", name);
  document
    .querySelector('link[rel="manifest"]')
    ?.setAttribute("href", `/manifest.webmanifest?name=${encodeURIComponent(name)}`);
}
