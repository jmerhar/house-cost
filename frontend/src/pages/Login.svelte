<script lang="ts">
  import { onMount } from "svelte";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { dismissed, passkeyOfferDeclined, passkeyUsedHere, rememberPasskeyUsed } from "../lib/passkeys";
  import { m } from "../paraglide/messages.js";

  let { onDone }: { onDone: () => void } = $props();
  const app = useApp();

  /** How long a passkey request waits in the autofill before it is renewed: inside the five
   *  minutes the server keeps its challenge. */
  const RENEW_MS = 240_000;

  const passkeys = app.authenticator.supported();
  // On a browser that has logged in with a passkey before, that is offered first.
  const passkeyFirst = passkeys && passkeyUsedHere();

  let login = $state("");
  let password = $state("");
  let busy = $state(false);
  let error = $state("");
  let autofill = false;
  let renew: ReturnType<typeof setTimeout> | undefined;
  let open = true;

  async function finishWithPasskey(answer: unknown): Promise<void> {
    app.me = await app.api.passkeyLogIn(answer);
    rememberPasskeyUsed();
    onDone();
  }

  /** Wait in the username field's autofill for the person to pick one of this site's passkeys. */
  async function listen(): Promise<void> {
    if (!autofill || !open) return;
    clearTimeout(renew);
    try {
      const options = await app.api.passkeyLoginOptions();
      renew = setTimeout(() => {
        app.authenticator.cancel();
        listen();
      }, RENEW_MS);
      const answer = await app.authenticator.authenticate(options, true);
      clearTimeout(renew);
      busy = true;
      await finishWithPasskey(answer);
    } catch (failure) {
      // Cancelled by the button, a renewal or leaving the page; anything else is worth saying.
      if (!dismissed(failure)) error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    if (passkeys) {
      app.authenticator.autofill().then(
        (supported) => {
          autofill = supported;
          listen();
        },
        () => undefined,
      );
    }
    return () => {
      open = false;
      clearTimeout(renew);
      if (autofill) app.authenticator.cancel();
    };
  });

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    error = "";
    try {
      app.me = await app.api.logIn(login, password);
      app.offerPasskey =
        passkeys && !passkeyUsedHere() && !passkeyOfferDeclined() && (await app.authenticator.builtIn().catch(() => false));
      onDone();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  async function withPasskey(): Promise<void> {
    clearTimeout(renew);
    if (autofill) app.authenticator.cancel();
    busy = true;
    error = "";
    try {
      const options = await app.api.passkeyLoginOptions();
      await finishWithPasskey(await app.authenticator.authenticate(options));
    } catch (failure) {
      if (!dismissed(failure)) error = errorMessage(failure);
      busy = false;
      listen();
    }
  }
</script>

<form class="card narrow" onsubmit={submit}>
  <h1>{m.app_name()}</h1>
  <h2>{m.login_title()}</h2>
  {#if passkeyFirst}
    <button type="button" class="wide-button" disabled={busy} onclick={withPasskey}>{m.login_passkey()}</button>
    <p class="muted or"><small>{m.login_or_password()}</small></p>
  {/if}
  <label>
    {m.field_login()}
    <input bind:value={login} required autocomplete="username webauthn" autocapitalize="none" />
  </label>
  <label>{m.field_password()}<input type="password" bind:value={password} required autocomplete="current-password" /></label>
  {#if error}<p role="alert">{error}</p>{/if}
  <div class="actions">
    <button type="submit" class:secondary={passkeyFirst} disabled={busy}>{busy ? m.logging_in() : m.login_submit()}</button>
    {#if passkeys && !passkeyFirst}
      <button type="button" class="secondary" disabled={busy} onclick={withPasskey}>{m.login_passkey()}</button>
    {/if}
  </div>
  {#if passkeys}<p class="muted"><small>{m.login_passkey_hint()}</small></p>{/if}
</form>
