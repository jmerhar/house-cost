<script lang="ts">
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { m } from "../paraglide/messages.js";

  let { onDone }: { onDone: () => void } = $props();
  const app = useApp();

  let login = $state("");
  let password = $state("");
  let busy = $state(false);
  let error = $state("");

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    error = "";
    try {
      app.me = await app.api.logIn(login, password);
      onDone();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }
</script>

<form class="card narrow" onsubmit={submit}>
  <h1>{m.app_name()}</h1>
  <h2>{m.login_title()}</h2>
  <label>{m.field_login()}<input bind:value={login} required autocomplete="username" autocapitalize="none" /></label>
  <label>{m.field_password()}<input type="password" bind:value={password} required autocomplete="current-password" /></label>
  {#if error}<p role="alert">{error}</p>{/if}
  <button type="submit" disabled={busy}>{m.login_submit()}</button>
</form>
