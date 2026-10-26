import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { errorMessage } from "./errors";
import { AppState } from "./state.svelte";
import { CATEGORIES, HOUSEHOLDS, MEMBER, fakeApi } from "../testing";

describe("errorMessage", () => {
  it("explains the API's own refusals", () => {
    expect(errorMessage(new ApiError(422, "no_rule"))).toBe("This category has no split for that date. Ask an administrator to add one.");
    expect(errorMessage(new ApiError(401, "invalid_login"))).toBe("Wrong username or password.");
  });

  it("says when the server cannot be reached", () => {
    expect(errorMessage(new ApiError(0, "Failed to fetch"))).toBe("The server cannot be reached. Check your internet connection and try again.");
  });

  it("passes on what it does not know", () => {
    expect(errorMessage(new ApiError(500, "Internal Server Error"))).toBe("Something went wrong (Internal Server Error). Try again.");
    expect(errorMessage(new Error("boom"))).toBe("Something went wrong (boom). Try again.");
    expect(errorMessage("odd")).toBe("Something went wrong (odd). Try again.");
  });
});

describe("AppState", () => {
  it("loads the households and categories and names them", async () => {
    const { api } = fakeApi({ "GET /households": HOUSEHOLDS, "GET /categories": CATEGORIES });
    const app = new AppState(api);
    await app.refresh();

    expect(app.household(2)).toBe("Tiago + Marta");
    expect(app.category(11)).toBe("Road upkeep");
    expect(app.household(99)).toBe("#99");
    expect(app.category(99)).toBe("#99");
  });

  it("knows whether the person is an admin", () => {
    const app = new AppState(fakeApi({}).api);
    expect(app.isAdmin).toBe(false);
    app.me = MEMBER;
    expect(app.isAdmin).toBe(false);
    app.me = { ...MEMBER, role: "admin" };
    expect(app.isAdmin).toBe(true);
  });
});
