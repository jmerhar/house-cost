import { afterEach, describe, expect, it, vi } from "vitest";
import { declinePasskeyOffer, passkeyOfferDeclined, passkeyUsedHere, rememberPasskeyUsed } from "./passkeys";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("what this browser remembers", () => {
  it("that a passkey was used here, and that the offer was turned down", () => {
    expect([passkeyUsedHere(), passkeyOfferDeclined()]).toEqual([false, false]);
    rememberPasskeyUsed();
    declinePasskeyOffer();
    expect([passkeyUsedHere(), passkeyOfferDeclined()]).toEqual([true, true]);
  });

  it("nothing, without failing, where storage is refused", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    rememberPasskeyUsed();
    expect(passkeyUsedHere()).toBe(false);
  });
});
