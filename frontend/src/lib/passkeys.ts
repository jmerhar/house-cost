/**
 * Passkeys in the browser: asking the device's authenticator to make one or to sign in with one.
 *
 * The browser's half of each ceremony is @simplewebauthn/browser's; this module gathers it in one
 * replaceable object, so views can be tested without a real authenticator.
 */

import {
  browserSupportsWebAuthn,
  browserSupportsWebAuthnAutofill,
  platformAuthenticatorIsAvailable,
  startAuthentication,
  startRegistration,
  WebAuthnAbortService,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";

export interface Authenticator {
  /** Whether this browser can use passkeys at all. */
  supported(): boolean;
  /** Whether the browser can offer passkeys among the username field's autofill suggestions. */
  autofill(): Promise<boolean>;
  /** Whether the device itself can make a passkey: a fingerprint, face or screen-lock reader. */
  builtIn(): Promise<boolean>;
  /** Make a passkey from the server's registration options; resolves to the answer to send back. */
  register(options: Record<string, unknown>): Promise<unknown>;
  /**
   * Sign in with a passkey from the server's options; resolves to the answer to send back. With
   * ``autofill``, the request waits quietly until the person picks a passkey from the username
   * field's suggestions.
   */
  authenticate(options: Record<string, unknown>, autofill?: boolean): Promise<unknown>;
  /** Stop a request that is waiting, which then rejects as an AbortError. */
  cancel(): void;
}

/** The browser's own authenticator. */
export const browserAuthenticator: Authenticator = {
  supported: browserSupportsWebAuthn,
  autofill: browserSupportsWebAuthnAutofill,
  builtIn: platformAuthenticatorIsAvailable,
  register: (options) => startRegistration({ optionsJSON: options as unknown as PublicKeyCredentialCreationOptionsJSON }),
  authenticate: (options, autofill = false) =>
    startAuthentication({
      optionsJSON: options as unknown as PublicKeyCredentialRequestOptionsJSON,
      useBrowserAutofill: autofill,
    }),
  cancel: () => WebAuthnAbortService.cancelCeremony(),
};

const USED = "house-cost:passkey-used";
const DECLINED = "house-cost:passkey-offer-declined";

function read(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function write(key: string): void {
  try {
    localStorage.setItem(key, "1");
  } catch {
    // A browser that keeps nothing simply asks again next time.
  }
}

/**
 * Whether someone has logged in with a passkey on this browser, which then offers it first. A
 * site cannot ask whether a passkey exists, so this is remembered instead.
 */
export const passkeyUsedHere = (): boolean => read(USED);
export const rememberPasskeyUsed = (): void => write(USED);

/** Whether the offer to set up a passkey after a password login was turned down on this browser. */
export const passkeyOfferDeclined = (): boolean => read(DECLINED);
export const declinePasskeyOffer = (): void => write(DECLINED);

/** Whether a ceremony failed because the person dismissed it, which needs no error message. */
export function dismissed(error: unknown): boolean {
  return error instanceof Error && (error.name === "NotAllowedError" || error.name === "AbortError");
}

/** A name for this device to label a passkey with, guessed from the browser: "iPhone", "Mac". */
export function deviceName(userAgent: string = navigator.userAgent): string {
  for (const [pattern, name] of [
    [/iPhone/, "iPhone"],
    [/iPad/, "iPad"],
    [/Android/, "Android"],
    [/Macintosh|Mac OS X/, "Mac"],
    [/Windows/, "Windows"],
    [/Linux/, "Linux"],
  ] as const) {
    if (pattern.test(userAgent)) return name;
  }
  return "Passkey";
}
