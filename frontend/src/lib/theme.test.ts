import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, chooseTheme, chosenTheme } from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.head.innerHTML = "";
  vi.restoreAllMocks();
});

function barTags(): HTMLMetaElement[] {
  for (const [media, content] of [["(prefers-color-scheme: light)", "#f7f6f2"], ["(prefers-color-scheme: dark)", "#17191b"]]) {
    document.head.append(Object.assign(document.createElement("meta"), { name: "theme-color", media, content }));
  }
  return [...document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')];
}

describe("theme", () => {
  it("follows the device until one is chosen, and remembers the choice", () => {
    expect(chosenTheme()).toBe("auto");
    chooseTheme("dark");
    expect([chosenTheme(), document.documentElement.dataset.theme]).toEqual(["dark", "dark"]);
    chooseTheme("auto");
    expect([chosenTheme(), document.documentElement.dataset.theme]).toEqual(["auto", undefined]);
    expect(localStorage.length).toBe(0);
  });

  it("colours the browser bar for a chosen theme, and per device setting otherwise", () => {
    const [light, dark] = barTags();
    applyTheme("dark");
    expect([light.content, dark.content]).toEqual(["#17191b", "#17191b"]);
    applyTheme("light");
    expect([light.content, dark.content]).toEqual(["#f7f6f2", "#f7f6f2"]);
    applyTheme("auto");
    expect([light.content, dark.content]).toEqual(["#f7f6f2", "#17191b"]);
  });

  it("ignores what it cannot read, and still shows a choice it cannot keep", () => {
    localStorage.setItem("house-cost:theme", "purple");
    expect(chosenTheme()).toBe("auto");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(chosenTheme()).toBe("auto");
    chooseTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
