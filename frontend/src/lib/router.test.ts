import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { followHistory, interceptLinks, match, navigate, route } from "./router.svelte";

beforeEach(() => {
  // Back to the root route between tests: the route is module state, shared by every test here.
  history.replaceState(null, "", "/elsewhere");
  navigate("/", { replace: true });
});
afterEach(() => {
  document.body.innerHTML = "";
});

describe("match", () => {
  it("reads parameters out of a path", () => {
    expect(match("/bills/:id", "/bills/42")).toEqual({ id: "42" });
    expect(match("/bills/:id", "/bills/a%20b")).toEqual({ id: "a b" });
    expect(match("/bills", "/bills/")).toEqual({});
  });

  it("does not match another path", () => {
    expect(match("/bills/:id", "/bills")).toBeNull();
    expect(match("/bills/:id", "/settlements/42")).toBeNull();
  });
});

describe("navigate", () => {
  it("shows the path and adds it to the history", () => {
    const push = vi.spyOn(history, "pushState");
    navigate("/bills");
    expect(route.path).toBe("/bills");
    expect(location.pathname).toBe("/bills");
    expect(push).toHaveBeenCalledOnce();
    push.mockRestore();
  });

  it("replaces the history entry when asked", () => {
    const replace = vi.spyOn(history, "replaceState");
    navigate("/bills/7", { replace: true });
    expect(route.path).toBe("/bills/7");
    expect(replace).toHaveBeenCalledOnce();
    replace.mockRestore();
  });

  it("keeps the query in the URL but not in the route", () => {
    navigate("/settlements?from=2&to=1");
    expect(route.path).toBe("/settlements");
    expect(location.search).toBe("?from=2&to=1");
  });

  it("does nothing for the URL already shown", () => {
    navigate("/bills");
    const push = vi.spyOn(history, "pushState");
    navigate("/bills");
    expect(push).not.toHaveBeenCalled();
    push.mockRestore();
  });
});

describe("followHistory", () => {
  it("follows the back button until stopped", () => {
    const stop = followHistory();
    history.pushState(null, "", "/reports");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(route.path).toBe("/reports");

    stop();
    history.pushState(null, "", "/activity");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(route.path).toBe("/reports");
  });
});

describe("interceptLinks", () => {
  function click(html: string, init: MouseEventInit = {}): MouseEvent {
    document.body.innerHTML = html;
    const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...init });
    document.querySelector("[data-target]")!.dispatchEvent(event);
    return event;
  }

  it("turns a click on the app's own link into a route change", () => {
    const stop = interceptLinks(document.body);
    const event = click('<a href="/bills"><span data-target>Bills</span></a>');
    expect(event.defaultPrevented).toBe(true);
    expect(route.path).toBe("/bills");
    stop();
  });

  it.each([
    ['<a href="https://elsewhere.test/" data-target>x</a>', {}],
    ['<a href="/api/attachments/1" data-target>x</a>', {}],
    ['<a href="/bills" target="_blank" data-target>x</a>', {}],
    ['<a href="/bills" download data-target>x</a>', {}],
    ['<a href="/bills" data-target>x</a>', { metaKey: true }],
    ['<a href="/bills" data-target>x</a>', { button: 1 }],
    ["<span data-target>not a link</span>", {}],
  ])("leaves %s to the browser", (html, init) => {
    const stop = interceptLinks(document.body);
    const event = click(html, init as MouseEventInit);
    expect(event.defaultPrevented).toBe(false);
    expect(route.path).toBe("/");
    stop();
  });

  it("leaves a click someone else already handled", () => {
    const stop = interceptLinks(document.body);
    document.body.innerHTML = '<a href="/bills" data-target>x</a>';
    const link = document.querySelector("a")!;
    link.addEventListener("click", (event) => event.preventDefault());
    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(route.path).toBe("/");
    stop();
  });

  it("stops intercepting when asked", () => {
    interceptLinks(document.body)();
    const event = click('<a href="/bills" data-target>x</a>');
    expect(event.defaultPrevented).toBe(false);
  });
});
