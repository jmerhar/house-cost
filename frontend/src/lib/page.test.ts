import { afterEach, describe, expect, it } from "vitest";
import { namePage } from "./page";

afterEach(() => {
  document.head.innerHTML = "";
});

describe("namePage", () => {
  it("names the tab and the home-screen app", () => {
    const meta = Object.assign(document.createElement("meta"), { name: "apple-mobile-web-app-title", content: "House costs" });
    document.head.append(meta);
    namePage("Despesas da casa");

    expect(document.title).toBe("Despesas da casa");
    expect(meta.getAttribute("content")).toBe("Despesas da casa");
  });

  it("names the tab when the page has no home-screen title", () => {
    namePage("House costs");
    expect(document.title).toBe("House costs");
  });
});
