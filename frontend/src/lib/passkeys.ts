/**
 * Passkeys in the browser: asking the device's authenticator to make one or to sign in with one.
 *
 * The browser's half of each ceremony is @simplewebauthn/browser's; this module gathers it in one
 * replaceable object, so views can be tested without a real authenticator.
 */

export { browserAuthenticator, deviceName, dismissed, type Authenticator } from "@jmerhar/jigkit/passkeys";
import { keepStored, readStored } from "@jmerhar/jigkit/storage";

const USED = "house-cost:passkey-used";
const DECLINED = "house-cost:passkey-offer-declined";

function read(key: string): boolean {
  return readStored(key) === "1";
}

/** A browser that keeps nothing simply asks again next time. */
function write(key: string): void {
  keepStored(key, "1");
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
