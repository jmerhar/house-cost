<script lang="ts">
  import FingerprintPattern from "@lucide/svelte/icons/fingerprint-pattern";
  import { LoginForm } from "@jmerhar/jigkit/auth/svelte";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { memory } from "../lib/passkeys";
  import { m } from "../paraglide/messages.js";

  let { onDone }: { onDone: () => void } = $props();
  const app = useApp();
</script>

<LoginForm
  title={app.appName}
  labels={{
    heading: m.login_title(),
    login: m.field_login(),
    password: m.field_password(),
    submit: m.login_submit(),
    submitting: m.logging_in(),
    passkey: m.login_passkey(),
    orPassword: m.login_or_password(),
  }}
  logIn={async (login, password) => {
    app.me = await app.api.logIn(login, password);
  }}
  passkeys={{
    options: () => app.api.passkeyLoginOptions(),
    logIn: async (answer) => {
      app.me = await app.api.passkeyLogIn(answer);
    },
  }}
  {memory}
  authenticator={app.authenticator}
  {errorMessage}
  onDone={({ offerPasskey }) => {
    app.offerPasskey = offerPasskey;
    onDone();
  }}
>
  {#snippet icon()}<FingerprintPattern />{/snippet}
</LoginForm>
