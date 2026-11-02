/**
 * Passkeys in the browser: the device's authenticator, from jigkit, and what this browser
 * remembers about passkeys under house-cost's keys.
 */

import { passkeyMemory } from "@jmerhar/jigkit/passkeys";

export { browserAuthenticator, deviceName, dismissed, type Authenticator } from "@jmerhar/jigkit/passkeys";

/** Whether a passkey was used on this browser, and whether the offer to set one up was declined. */
export const memory = passkeyMemory("house-cost");

export const passkeyUsedHere = (): boolean => memory.usedHere();
export const rememberPasskeyUsed = (): void => memory.rememberUsed();
export const passkeyOfferDeclined = (): boolean => memory.offerDeclined();
export const declinePasskeyOffer = (): void => memory.declineOffer();
