import { afterEach, describe, expect, it, vi } from "vitest";

const cancelCeremony = vi.fn();
vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  browserSupportsWebAuthnAutofill: async () => true,
  platformAuthenticatorIsAvailable: async () => false,
  startRegistration: vi.fn(async ({ optionsJSON }) => ({ made: optionsJSON.challenge })),
  startAuthentication: vi.fn(async ({ optionsJSON, useBrowserAutofill }) => ({
    signed: optionsJSON.challenge,
    autofill: useBrowserAutofill,
  })),
  WebAuthnAbortService: { cancelCeremony: () => cancelCeremony() },
}));

const {
  browserAuthenticator,
  declinePasskeyOffer,
  deviceName,
  dismissed,
  passkeyOfferDeclined,
  passkeyUsedHere,
  rememberPasskeyUsed,
} = await import("./passkeys");

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("browserAuthenticator", () => {
  it("hands the server's options to the browser's ceremonies", async () => {
    expect(browserAuthenticator.supported()).toBe(true);
    expect(await browserAuthenticator.autofill()).toBe(true);
    expect(await browserAuthenticator.builtIn()).toBe(false);
    expect(await browserAuthenticator.register({ challenge: "abc" })).toEqual({ made: "abc" });
    expect(await browserAuthenticator.authenticate({ challenge: "xyz" })).toEqual({ signed: "xyz", autofill: false });
    expect(await browserAuthenticator.authenticate({ challenge: "xyz" }, true)).toEqual({ signed: "xyz", autofill: true });
    browserAuthenticator.cancel();
    expect(cancelCeremony).toHaveBeenCalledOnce();
  });
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

describe("dismissed", () => {
  it("recognises a ceremony the person cancelled", () => {
    expect(dismissed(Object.assign(new Error("x"), { name: "NotAllowedError" }))).toBe(true);
    expect(dismissed(Object.assign(new Error("x"), { name: "AbortError" }))).toBe(true);
    expect(dismissed(new Error("other"))).toBe(false);
    expect(dismissed("NotAllowedError")).toBe(false);
  });
});

describe("deviceName", () => {
  it.each([
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone"],
    ["Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)", "iPad"],
    ["Mozilla/5.0 (Linux; Android 15; Pixel 9)", "Android"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0)", "Mac"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Windows"],
    ["Mozilla/5.0 (X11; Linux x86_64)", "Linux"],
    ["curl/8", "Passkey"],
  ])("names %s %s", (agent, name) => {
    expect(deviceName(agent)).toBe(name);
  });

  it("reads this browser by default", () => {
    expect(typeof deviceName()).toBe("string");
  });
});
