import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.svelte";
import { LANGUAGE_KEY } from "./lib/language";
import { navigate } from "./lib/router.svelte";
import { ADMIN, CATEGORIES, HOUSEHOLDS, MEMBER, aBill, fakeApi, refuse } from "./testing";

/** The routes every logged-in view needs. */
const LOGGED_IN = {
  "GET /setup": { required: false },
  "GET /households": HOUSEHOLDS,
  "GET /categories": CATEGORIES,
  "GET /balances": { households: [], transfers: [] },
  "GET /bills": { items: [aBill()], total: 1 },
  "GET /reports/summary": { year: 2026, years: [2026], total_cents: 0, shares: [], categories: [], months: [] },
};

beforeEach(() => {
  history.replaceState(null, "", "/elsewhere");
  navigate("/", { replace: true });
});
afterEach(() => localStorage.clear());

describe("App", () => {
  it("asks for setup on a fresh install", async () => {
    const { api } = fakeApi({ "GET /setup": { required: true } });
    render(App, { api });
    expect(await screen.findByRole("heading", { name: "Set up House costs" })).toBeInTheDocument();
  });

  it("asks for a login when nobody is logged in, then shows the balances", async () => {
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": refuse(401, "not_authenticated"), "POST /auth/login": MEMBER });
    render(App, { api });

    await fireEvent.input(await screen.findByLabelText("Login"), { target: { value: "tiago" } });
    await fireEvent.input(screen.getByLabelText("Password"), { target: { value: "correct horse battery" } });
    await fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("heading", { name: "Balances" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("shows an admin the admin pages, and the reconciliation page when it is on", async () => {
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": { ...ADMIN, reconciliation_enabled: true } });
    render(App, { api });

    expect(await screen.findByRole("link", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reconciliation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Balances" })).toHaveAttribute("aria-current", "page");
  });

  it("follows links between views without reloading", async () => {
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": ADMIN });
    render(App, { api });

    await fireEvent.click(await screen.findByRole("link", { name: "Bills" }));
    expect(await screen.findByRole("heading", { name: "Bills" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bills" })).toHaveAttribute("aria-current", "page");
  });

  it.each([
    ["/bills/new", "New bill"],
    ["/settlements", "Settlements"],
    ["/reports", "Reports"],
    ["/activity", "Activity"],
    ["/account", "Your account"],
    ["/admin", "Admin"],
  ])("routes %s", async (path, heading) => {
    const { api } = fakeApi({
      ...LOGGED_IN,
      "GET /auth/me": ADMIN,
      "GET /settlements": [],
      "GET /audit": { items: [], total: 0 },
      "GET /auth/sessions": [],
      "GET /people": [],
      "GET /rules": [],
    });
    navigate(path);
    render(App, { api });
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("opens a bill at its own address", async () => {
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": ADMIN, "GET /bills/7": aBill() });
    navigate("/bills/7");
    render(App, { api });
    expect(await screen.findByRole("heading", { name: "Edit bill" })).toBeInTheDocument();
  });

  it("keeps members out of the admin pages and the reconciliation page while it is off", async () => {
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": MEMBER });
    navigate("/admin");
    render(App, { api });
    expect(await screen.findByText("There is nothing here.")).toBeInTheDocument();
    navigate("/reconciliation");
    expect(await screen.findByText("There is nothing here.")).toBeInTheDocument();
  });

  it("logs out", async () => {
    const { api, calls } = fakeApi({ ...LOGGED_IN, "GET /auth/me": ADMIN, "POST /auth/logout": () => undefined });
    render(App, { api });
    await fireEvent.click(await screen.findByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/auth/logout")).toBe(true);
  });

  it("switches to the language saved on the account", async () => {
    const reload = vi.fn();
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": { ...ADMIN, language: "pt-PT" } });
    render(App, { api, reload });

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("pt-PT");
  });

  it("does not reload when the browser already has the account's language", async () => {
    localStorage.setItem(LANGUAGE_KEY, "en");
    const reload = vi.fn();
    const { api } = fakeApi({ ...LOGGED_IN, "GET /auth/me": { ...ADMIN, language: "en" } });
    render(App, { api, reload });

    expect(await screen.findByRole("heading", { name: "Balances" })).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });

  it("switches language after a login too", async () => {
    const reload = vi.fn();
    const { api } = fakeApi({
      ...LOGGED_IN,
      "GET /auth/me": refuse(401, "not_authenticated"),
      "POST /auth/login": { ...MEMBER, language: "pt-PT" },
    });
    render(App, { api, reload });
    await fireEvent.input(await screen.findByLabelText("Login"), { target: { value: "tiago" } });
    await fireEvent.input(screen.getByLabelText("Password"), { target: { value: "x".repeat(10) } });
    await fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
  });

  it("says so when the server cannot be reached", async () => {
    const { api } = fakeApi({ "GET /setup": () => Promise.reject(new TypeError("Failed to fetch")) });
    render(App, { api });
    expect(await screen.findByRole("alert")).toHaveTextContent("The server cannot be reached.");
  });
});
