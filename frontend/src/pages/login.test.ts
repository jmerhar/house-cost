import { cleanup, fireEvent, screen, waitFor } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import PasskeyOffer from "../lib/PasskeyOffer.svelte";
import { passkeyOfferDeclined, passkeyUsedHere, rememberPasskeyUsed, type Authenticator } from "../lib/passkeys";
import { ADMIN, MEMBER, appFor, fakeApi, fakeAuthenticator, refuse, renderPage } from "../testing";
import Login from "./Login.svelte";

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

const cancelled = () => Object.assign(new Error("cancelled"), { name: "AbortError" });

/** An authenticator whose autofill request waits until ``pick`` answers it or ``cancel`` stops it. */
function autofilling() {
  let answer: ((value: unknown) => void) | undefined;
  let stop: ((error: Error) => void) | undefined;
  const requests: boolean[] = [];
  const authenticator: Authenticator = {
    ...fakeAuthenticator({ pressed: true }),
    autofill: async () => true,
    authenticate: (_options, autofill = false) => {
      requests.push(autofill);
      if (!autofill) return Promise.resolve({ pressed: true });
      return new Promise((resolve, reject) => {
        answer = resolve;
        stop = reject;
      });
    },
    cancel: vi.fn(() => stop?.(cancelled())),
  };
  return { authenticator, requests, pick: (value: unknown) => answer?.(value) };
}

describe("logging in with a passkey", () => {
  it("is offered among the username's autofill suggestions", async () => {
    const onDone = vi.fn();
    const { api, calls } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" }, "POST /auth/passkey-login": MEMBER });
    const passkey = autofilling();
    const app = appFor(api, ADMIN, passkey.authenticator);
    renderPage(Login, app, { onDone });

    expect(screen.getByLabelText("Username")).toHaveAttribute("autocomplete", "username webauthn");
    await waitFor(() => expect(passkey.requests).toEqual([true]));
    passkey.pick({ picked: true });

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(calls.at(-1)!.body).toEqual({ credential: { picked: true } });
    expect(app.me).toEqual(MEMBER);
    expect(passkeyUsedHere()).toBe(true);
  });

  it("renews the waiting request before the server forgets its challenge, and stops it on leaving", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { api, calls } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" } });
    const passkey = autofilling();
    const { unmount } = renderPage(Login, appFor(api, ADMIN, passkey.authenticator), { onDone: vi.fn() });
    await waitFor(() => expect(passkey.requests).toEqual([true]));

    vi.advanceTimersByTime(240_000);
    await waitFor(() => expect(passkey.requests).toEqual([true, true]));
    expect(calls.filter((c) => c.path === "/auth/passkey-login/options")).toHaveLength(2);

    unmount();
    expect(passkey.authenticator.cancel).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(240_000);
    expect(passkey.requests).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("stops the waiting request for the button, and waits again if the button is cancelled", async () => {
    const { api } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" } });
    const passkey = autofilling();
    passkey.authenticator.authenticate = (_options, autofill = false) => {
      passkey.requests.push(autofill);
      return autofill ? new Promise(() => undefined) : Promise.reject(Object.assign(new Error("no"), { name: "NotAllowedError" }));
    };
    renderPage(Login, appFor(api, ADMIN, passkey.authenticator), { onDone: vi.fn() });
    await waitFor(() => expect(passkey.requests).toEqual([true]));

    await fireEvent.click(screen.getByRole("button", { name: "Log in with fingerprint or face" }));
    await waitFor(() => expect(passkey.requests).toEqual([true, false, true]));
    expect(passkey.authenticator.cancel).toHaveBeenCalled();
  });

  it("says what went wrong with a picked passkey", async () => {
    const { api } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" }, "POST /auth/passkey-login": refuse(401, "passkey_unknown") });
    const passkey = autofilling();
    renderPage(Login, appFor(api, ADMIN, passkey.authenticator), { onDone: vi.fn() });
    await waitFor(() => expect(passkey.requests).toEqual([true]));
    passkey.pick({ picked: true });

    expect(await screen.findByRole("alert")).toHaveTextContent("not linked to any account");
  });

  it("falls back to the button when the browser cannot say whether it autofills", async () => {
    const { api, calls } = fakeApi({});
    renderPage(Login, appFor(api, ADMIN, { ...fakeAuthenticator(), autofill: () => Promise.reject(new Error("odd")) }), {
      onDone: vi.fn(),
    });
    await Promise.resolve();
    expect(calls).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Log in with fingerprint or face" })).toBeInTheDocument();
  });

  it("comes first on a browser that has used one before", () => {
    rememberPasskeyUsed();
    const { api } = fakeApi({});
    renderPage(Login, appFor(api, ADMIN, fakeAuthenticator()), { onDone: vi.fn() });

    const buttons = screen.getAllByRole("button").map((button) => button.textContent?.trim());
    expect(buttons).toEqual(["Log in with fingerprint or face", "Log in"]);
    expect(screen.getByText("or with your password")).toBeInTheDocument();
  });
});

describe("the offer after a password login", () => {
  async function logInWithPassword(authenticator: Authenticator) {
    cleanup();
    const { api } = fakeApi({ "POST /auth/login": ADMIN });
    const app = appFor(api, ADMIN, authenticator);
    app.me = null;
    renderPage(Login, app, { onDone: vi.fn() });
    await fireEvent.input(screen.getByLabelText("Username"), { target: { value: "lucia" } });
    await fireEvent.input(screen.getByLabelText("Password"), { target: { value: "a password" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Log in" }).closest("form")!);
    await waitFor(() => expect(app.me).toEqual(ADMIN));
    return app;
  }

  it("is made on a device that can make a passkey", async () => {
    expect((await logInWithPassword(fakeAuthenticator())).offerPasskey).toBe(true);
  });

  it("is not made without a fingerprint or face reader, once turned down, or once a passkey was used", async () => {
    expect((await logInWithPassword({ ...fakeAuthenticator(), builtIn: async () => false })).offerPasskey).toBe(false);
    expect(
      (await logInWithPassword({ ...fakeAuthenticator(), builtIn: () => Promise.reject(new Error("odd")) })).offerPasskey,
    ).toBe(false);
    localStorage.setItem("house-cost:passkey-offer-declined", "1");
    expect((await logInWithPassword(fakeAuthenticator())).offerPasskey).toBe(false);
    localStorage.clear();
    rememberPasskeyUsed();
    expect((await logInWithPassword(fakeAuthenticator())).offerPasskey).toBe(false);
  });

  it("sets one up in one tap", async () => {
    const { api, calls } = fakeApi({
      "POST /auth/passkeys/options": { challenge: "r" },
      "POST /auth/passkeys": { id: 1, label: "Android", created_at: "2026-10-26T20:00:00Z", last_used_at: null },
    });
    const app = appFor(api, ADMIN, fakeAuthenticator({ made: true }));
    app.offerPasskey = true;
    renderPage(PasskeyOffer, app);

    expect(screen.getByText("Log in faster next time with your fingerprint or face?")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Set it up" }));

    expect(await screen.findByText(/All set/)).toBeInTheDocument();
    expect((calls.at(-1)!.body as { credential: unknown }).credential).toEqual({ made: true });
    expect(passkeyUsedHere()).toBe(true);
    await fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(app.offerPasskey).toBe(false);
  });

  it("is turned down for this browser", async () => {
    const app = appFor(fakeApi({}).api);
    app.offerPasskey = true;
    renderPage(PasskeyOffer, app);
    await fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(app.offerPasskey).toBe(false);
    expect(passkeyOfferDeclined()).toBe(true);
  });

  it("goes away when the device already has one, says nothing when cancelled, and explains a refusal", async () => {
    let refusal = refuse(409, "passkey_exists");
    const { api } = fakeApi({ "POST /auth/passkeys/options": { challenge: "r" }, "POST /auth/passkeys": () => refusal });
    let current = fakeAuthenticator({ made: true });
    const switchable: Authenticator = { ...current, register: (options) => current.register(options) };
    const app = appFor(api, ADMIN, switchable);
    app.offerPasskey = true;
    renderPage(PasskeyOffer, app);
    await fireEvent.click(screen.getByRole("button", { name: "Set it up" }));
    await waitFor(() => expect(app.offerPasskey).toBe(false));
    expect(passkeyUsedHere()).toBe(true);

    app.offerPasskey = true;
    current = fakeAuthenticator(undefined, Object.assign(new Error("x"), { name: "NotAllowedError" }));
    await fireEvent.click(await screen.findByRole("button", { name: "Set it up" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Set it up" })).toBeEnabled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    refusal = refuse(400, "passkey_rejected");
    current = fakeAuthenticator({ made: true });
    await fireEvent.click(screen.getByRole("button", { name: "Set it up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be verified");
  });
});
