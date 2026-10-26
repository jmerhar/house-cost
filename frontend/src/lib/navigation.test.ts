import { fireEvent, screen, waitFor } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ADMIN, MEMBER, appFor, fakeApi, renderPage } from "../testing";
import Navigation from "./Navigation.svelte";
import { navigate } from "./router.svelte";

afterEach(() => {
  navigate("/", { replace: true });
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

function show(me = ADMIN, path = "/") {
  navigate(path, { replace: true });
  const onLogOut = vi.fn();
  const app = appFor(fakeApi({}).api, me);
  renderPage(Navigation, app, { onLogOut });
  return { app, onLogOut };
}

describe("Navigation", () => {
  it("shows the everyday pages and keeps the rest in More and the account menu", async () => {
    show();
    const links = screen.getAllByRole("link").map((link) => link.textContent?.trim());
    expect(links).toEqual(["House costs", "Balances", "Bills", "Settlements", "Reports"]);

    await fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/documents");
    expect(screen.queryByRole("link", { name: "Reconciliation" })).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Lúcia" }));
    expect(screen.queryByRole("link", { name: "Documents" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/admin");
  });

  it("closes a menu on Escape, on a click outside it, and when a page opens", async () => {
    show();
    const more = screen.getByRole("button", { name: "More" });
    await fireEvent.click(more);
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(more).toHaveAttribute("aria-expanded", "false");

    await fireEvent.click(more);
    await fireEvent.click(document.body);
    expect(more).toHaveAttribute("aria-expanded", "false");

    await fireEvent.click(more);
    await fireEvent.click(screen.getByRole("link", { name: "Bills" }));
    navigate("/bills");
    await waitFor(() => expect(more).toHaveAttribute("aria-expanded", "false"));

    await fireEvent.click(more);
    await fireEvent.click(more);
    expect(more).toHaveAttribute("aria-expanded", "false");
  });

  it("marks More while one of its pages is open, and the page inside it", async () => {
    show(ADMIN, "/documents");
    const more = screen.getByRole("button", { name: "More" });
    expect(more).toHaveClass("current");
    await fireEvent.click(more);
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
  });

  it("offers members no settings, and logs out", async () => {
    const { onLogOut } = show({ ...MEMBER, reconciliation_enabled: true }, "/account");
    await fireEvent.click(screen.getByRole("button", { name: "Tiago" }));
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(onLogOut).toHaveBeenCalledOnce();

    await fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("link", { name: "Reconciliation" })).toBeInTheDocument();
  });

  it("chooses light, dark or the device's own look from the account menu", async () => {
    show();
    await fireEvent.click(screen.getByRole("button", { name: "Lúcia" }));
    expect(screen.getByRole("button", { name: "Same as this device" })).toHaveAttribute("aria-pressed", "true");

    await fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("house-cost:theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Lúcia" })).toHaveAttribute("aria-expanded", "true");

    await fireEvent.click(screen.getByRole("button", { name: "Same as this device" }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("uses the name the app was given", () => {
    navigate("/", { replace: true });
    const app = appFor(fakeApi({}).api);
    app.title = "Oliveiras";
    renderPage(Navigation, app, { onLogOut: vi.fn() });
    expect(screen.getByRole("link", { name: "Oliveiras" })).toHaveAttribute("href", "/");
  });
});
