import { afterEach, describe, expect, it } from "vitest";
import { namePage } from "./page";

afterEach(() => {
  document.head.innerHTML = "";
});

describe("namePage", () => {
  it("names the tab and the home-screen app, and gives the manifest an address of its name", () => {
    const meta = Object.assign(document.createElement("meta"), { name: "apple-mobile-web-app-title", content: "House costs" });
    const manifest = Object.assign(document.createElement("link"), { rel: "manifest" });
    manifest.setAttribute("href", "/manifest.webmanifest");
    document.head.append(meta, manifest);
    namePage("Oliveiras & Co");

    expect(document.title).toBe("Oliveiras & Co");
    expect(meta.getAttribute("content")).toBe("Oliveiras & Co");
    expect(manifest.getAttribute("href")).toBe("/manifest.webmanifest?name=Oliveiras%20%26%20Co");
  });

  it("names the tab when the page has no home-screen title", () => {
    namePage("House costs");
    expect(document.title).toBe("House costs");
  });
});
