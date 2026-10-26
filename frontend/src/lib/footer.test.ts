import { screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import { appFor, fakeApi, refuse, renderPage } from "../testing";
import Footer from "./Footer.svelte";

const HEALTH = { status: "ok", database: "connected", version: "0.8.0" };

describe("Footer", () => {
  it("names the version and links the commit the image was built from", async () => {
    const { api } = fakeApi({ "GET /health": { ...HEALTH, revision: "0048894abcdef1234" } });
    renderPage(Footer, appFor(api));

    expect(await screen.findByText(/House costs 0\.8\.0/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "0048894" })).toHaveAttribute(
      "href",
      "https://github.com/jmerhar/house-cost/commit/0048894abcdef1234",
    );
  });

  it("shows only the version outside a CI build", async () => {
    const { api } = fakeApi({ "GET /health": { ...HEALTH, revision: null } });
    renderPage(Footer, appFor(api));

    expect(await screen.findByText(/House costs 0\.8\.0/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("stays empty when the server cannot say", async () => {
    const { api, calls } = fakeApi({ "GET /health": refuse(503, "down") });
    const { container } = renderPage(Footer, appFor(api));

    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls).toHaveLength(1);
    expect(container.querySelector("footer")).toBeNull();
  });
});
