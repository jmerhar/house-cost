/**
 * Passkeys in the browser: asking the device's authenticator to make one or to sign in with one.
 *
 * The browser's half of each ceremony is @simplewebauthn/browser's; this module gathers it in one
 * replaceable object, so views can be tested without a real authenticator.
 */

import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";

export interface Authenticator {
  /** Whether this browser can use passkeys at all. */
  supported(): boolean;
  /** Make a passkey from the server's registration options; resolves to the answer to send back. */
  register(options: Record<string, unknown>): Promise<unknown>;
  /** Sign in with a passkey from the server's options; resolves to the answer to send back. */
  authenticate(options: Record<string, unknown>): Promise<unknown>;
}

/** The browser's own authenticator. */
export const browserAuthenticator: Authenticator = {
  supported: browserSupportsWebAuthn,
  register: (options) => startRegistration({ optionsJSON: options as unknown as PublicKeyCredentialCreationOptionsJSON }),
  authenticate: (options) =>
    startAuthentication({ optionsJSON: options as unknown as PublicKeyCredentialRequestOptionsJSON }),
};

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
