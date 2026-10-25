<script lang="ts">
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { chosenLanguage } from "../lib/language";
  import { m } from "../paraglide/messages.js";

  let { onDone }: { onDone: () => void } = $props();
  const app = useApp();

  let household = $state("");
  let name = $state("");
  let login = $state("");
  let password = $state("");
  let busy = $state(false);
  let error = $state("");

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    error = "";
    try {
      app.me = await app.api.setUp({
        household_name: household,
        name,
        login,
        password,
        language: chosenLanguage(),
      });
      onDone();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }
</script>

<form class="card narrow" onsubmit={submit}>
  <h1>{m.setup_title()}</h1>
  <p>{m.setup_intro()}</p>
  <label>{m.field_household_name()}<input bind:value={household} required maxlength="100" /></label>
  <label>{m.field_name()}<input bind:value={name} required maxlength="100" autocomplete="name" /></label>
  <label>{m.field_login()}<input bind:value={login} required maxlength="100" autocomplete="username" autocapitalize="none" /></label>
  <label>
    {m.field_password()}
    <input type="password" bind:value={password} required minlength="10" autocomplete="new-password" />
    <small>{m.field_password_hint()}</small>
  </label>
  {#if error}<p role="alert">{error}</p>{/if}
  <button type="submit" disabled={busy}>{busy ? m.saving() : m.setup_submit()}</button>
</form>
