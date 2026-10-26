import { describe, expect, it, vi } from "vitest";

vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  startRegistration: vi.fn(async ({ optionsJSON }) => ({ made: optionsJSON.challenge })),
  startAuthentication: vi.fn(async ({ optionsJSON }) => ({ signed: optionsJSON.challenge })),
}));

const { browserAuthenticator, deviceName, dismissed } = await import("./passkeys");

describe("browserAuthenticator", () => {
  it("hands the server's options to the browser's ceremonies", async () => {
    expect(browserAuthenticator.supported()).toBe(true);
    expect(await browserAuthenticator.register({ challenge: "abc" })).toEqual({ made: "abc" });
    expect(await browserAuthenticator.authenticate({ challenge: "xyz" })).toEqual({ signed: "xyz" });
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
