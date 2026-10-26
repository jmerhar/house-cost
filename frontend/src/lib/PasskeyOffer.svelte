<script lang="ts">
  // After a password login on a device with a fingerprint, face or screen-lock reader: an offer to
  // log in with it next time, set up in one tap instead of from the account page.
  import { ApiError } from "./api";
  import { useApp } from "./context";
  import { errorMessage } from "./errors";
  import { declinePasskeyOffer, deviceName, dismissed, rememberPasskeyUsed } from "./passkeys";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
  let busy = $state(false);
  let done = $state(false);
  let error = $state("");

  async function accept(): Promise<void> {
    busy = true;
    error = "";
    try {
      const options = await app.api.passkeyOptions();
      await app.api.addPasskey(deviceName(), await app.authenticator.register(options));
      rememberPasskeyUsed();
      done = true;
    } catch (failure) {
      if (failure instanceof ApiError && failure.message === "passkey_exists") {
        // This device has one already: nothing to offer.
        rememberPasskeyUsed();
        app.offerPasskey = false;
      } else if (!dismissed(failure)) {
        error = errorMessage(failure);
      }
    } finally {
      busy = false;
    }
  }

  function later(): void {
    declinePasskeyOffer();
    app.offerPasskey = false;
  }
</script>

{#if app.offerPasskey}
  <div class="note offer" role="status">
    <p>{done ? m.passkey_offer_done() : m.passkey_offer()}</p>
    {#if error}<p role="alert">{error}</p>{/if}
    <div class="actions">
      {#if done}
        <button type="button" class="secondary" onclick={() => (app.offerPasskey = false)}>{m.close()}</button>
      {:else}
        <button type="button" disabled={busy} onclick={accept}>{m.passkey_offer_accept()}</button>
        <button type="button" class="secondary" disabled={busy} onclick={later}>{m.passkey_offer_later()}</button>
      {/if}
    </div>
  </div>
{/if}
