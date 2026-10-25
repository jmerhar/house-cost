/**
 * The interface's routes: the URL's path, kept in sync with the browser's history.
 *
 * The API serves the interface's shell for any path outside /api, so every view has a real URL
 * that can be bookmarked, shared and reloaded.
 */

let current = $state(typeof location === "undefined" ? "/" : location.pathname);

/** The path being shown. */
export const route = {
  get path(): string {
    return current;
  },
};

/**
 * Show another path, adding it to the history unless ``replace`` is set. A query string travels in
 * the URL, where a view reads it from `location.search`; the route itself is the path alone.
 */
export function navigate(path: string, { replace = false }: { replace?: boolean } = {}): void {
  if (path === location.pathname + location.search) return;
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  current = location.pathname;
  window.scrollTo?.(0, 0);
}

/** Follow the browser's back and forward buttons. Returns a function that stops following. */
export function followHistory(): () => void {
  const onPop = () => {
    current = location.pathname;
  };
  window.addEventListener("popstate", onPop);
  return () => window.removeEventListener("popstate", onPop);
}

/**
 * The parameters ``path`` gives ``pattern``, or null when it does not match.
 * `match("/bills/:id", "/bills/42")` is `{ id: "42" }`.
 */
export function match(pattern: string, path: string): Record<string, string> | null {
  const want = pattern.split("/").filter(Boolean);
  const have = path.split("/").filter(Boolean);
  if (want.length !== have.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < want.length; i++) {
    if (want[i].startsWith(":")) params[want[i].slice(1)] = decodeURIComponent(have[i]);
    else if (want[i] !== have[i]) return null;
  }
  return params;
}

/**
 * Turns clicks on the interface's own links into route changes rather than page loads. A link
 * opened in a new tab, with a modifier key, or to another site is left to the browser, and so
 * are links into /api (files, the CSV export).
 */
export function interceptLinks(root: HTMLElement): () => void {
  const onClick = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    const link = (event.target as Element | null)?.closest?.("a");
    if (!link || link.target || link.hasAttribute("download")) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
    event.preventDefault();
    navigate(url.pathname + url.search);
  };
  root.addEventListener("click", onClick);
  return () => root.removeEventListener("click", onClick);
}
