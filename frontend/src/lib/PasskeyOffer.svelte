<script lang="ts">
  // After a password login on a device with a fingerprint, face or screen-lock reader: an offer to
  // log in with it next time, set up in one tap instead of from the account page.
  import { PasskeyOffer } from "@jmerhar/jigkit/auth/svelte";
  import { useApp } from "./context";
  import { errorMessage } from "./errors";
  import { memory } from "./passkeys";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
</script>

<PasskeyOffer
  bind:open={app.offerPasskey}
  labels={{
    offer: m.passkey_offer(),
    done: m.passkey_offer_done(),
    accept: m.passkey_offer_accept(),
    later: m.passkey_offer_later(),
    close: m.close(),
  }}
  registration={{ options: () => app.api.passkeyOptions(), add: (label, credential) => app.api.addPasskey(label, credential) }}
  {memory}
  authenticator={app.authenticator}
  {errorMessage}
/>
