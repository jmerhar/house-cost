<script lang="ts">
  import { SetupForm } from "@jmerhar/jigkit/auth/svelte";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { chosenLanguage } from "../lib/language";
  import { m } from "../paraglide/messages.js";

  let { onDone }: { onDone: () => void } = $props();
  const app = useApp();

  let household = $state("");
</script>

<SetupForm
  labels={{
    heading: m.setup_title(),
    intro: m.setup_intro(),
    name: m.field_name(),
    login: m.field_login(),
    password: m.field_password(),
    passwordHint: m.field_password_hint(),
    submit: m.setup_submit(),
    submitting: m.saving(),
  }}
  setUp={async ({ name, login, password }) => {
    app.me = await app.api.setUp({ household_name: household, name, login, password, language: chosenLanguage() });
  }}
  {errorMessage}
  {onDone}
>
  <label>{m.field_household_name()}<input bind:value={household} required maxlength="100" /></label>
</SetupForm>
