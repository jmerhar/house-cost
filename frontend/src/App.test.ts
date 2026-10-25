import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App.svelte";
import { Api, ApiError, type Health } from "./lib/api";
import { LANGUAGE_KEY } from "./lib/language";

function apiAnswering(health: Promise<Health>): Api {
  const api = new Api();
  vi.spyOn(api, "health").mockReturnValue(health);
  return api;
}

afterEach(() => localStorage.clear());

describe("App", () => {
  it("names itself and shows the server's version", async () => {
    render(App, {
      api: apiAnswering(Promise.resolve({ status: "ok", database: "connected", version: "0.1.0" })),
    });

    expect(screen.getByRole("heading", { name: "House costs" })).toBeInTheDocument();
    expect(await screen.findByText("Server 0.1.0")).toBeInTheDocument();
  });

  it("says so when the server cannot be reached", async () => {
    render(App, { api: apiAnswering(Promise.reject(new ApiError(0, "Failed to fetch"))) });

    expect(await screen.findByRole("alert")).toHaveTextContent("The server cannot be reached.");
  });

  it("keeps a chosen language and reloads into it", async () => {
    const reload = vi.fn();
    render(App, { api: apiAnswering(new Promise(() => {})), reload });

    await fireEvent.change(screen.getByLabelText("Language"), { target: { value: "pt-PT" } });

    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("pt-PT");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("can go back to following the browser", async () => {
    localStorage.setItem(LANGUAGE_KEY, "pt-PT");
    const reload = vi.fn();
    render(App, { api: apiAnswering(new Promise(() => {})), reload });

    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("pt-PT");
    await fireEvent.change(select, { target: { value: "" } });

    expect(localStorage.getItem(LANGUAGE_KEY)).toBeNull();
    expect(reload).toHaveBeenCalledOnce();
  });
});
