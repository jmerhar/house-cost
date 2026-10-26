<script lang="ts">
  import { onMount } from "svelte";
  import type { Passkey, SessionOut } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { moment } from "../lib/format";
  import { LANGUAGE_NAMES, chooseLanguage } from "../lib/language";
  import { deviceName, dismissed } from "../lib/passkeys";
  import { m } from "../paraglide/messages.js";
  import { locales, type Locale } from "../paraglide/runtime.js";

  let { reload = () => location.reload() }: { reload?: () => void } = $props();
  const app = useApp();

  let name = $state(app.me?.name ?? "");
  let language = $state<string>(app.me?.language ?? "");
  let currentPassword = $state("");
  let newPassword = $state("");
  let sessions = $state<SessionOut[]>([]);
  let passkeys = $state<Passkey[]>([]);
  let error = $state("");
  let notice = $state("");
  let busy = $state(false);

  /** The notifications a person can turn on or off, with their labels. */
  const EVENTS = [
    ["new_bill", m.notify_new_bill],
    ["price_change", m.notify_price_change],
    ["contract", m.notify_contract],
    ["missing_bill", m.notify_missing_bill],
  ] as const;
  type Event = (typeof EVENTS)[number][0];

  let email = $state(app.me?.email ?? "");
  let phone = $state(app.me?.phone ?? "");
  const channels = $derived(app.me?.notify_channels ?? []);
  let notifyOn = $state<Record<Event, boolean>>({
    new_bill: true,
    price_change: true,
    contract: true,
    missing_bill: true,
    ...app.me?.notify_on,
  });
  let notifyError = $state("");
  let notifyNotice = $state("");
  let notifyBusy = $state(false);

  async function loadSessions(): Promise<void> {
    try {
      sessions = await app.api.sessions();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function loadPasskeys(): Promise<void> {
    try {
      passkeys = await app.api.passkeys();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  onMount(() => {
    loadSessions();
    loadPasskeys();
  });

  async function addPasskey(): Promise<void> {
    error = "";
    notice = "";
    try {
      const options = await app.api.passkeyOptions();
      const credential = await app.authenticator.register(options);
      const label = prompt(m.passkey_label(), deviceName())?.trim() || deviceName();
      passkeys = [...passkeys, await app.api.addPasskey(label, credential)];
      notice = m.passkey_added();
    } catch (failure) {
      if (!dismissed(failure)) error = errorMessage(failure);
    }
  }

  async function removePasskey(passkey: Passkey): Promise<void> {
    if (!confirm(m.confirm_remove_passkey())) return;
    try {
      await app.api.removePasskey(passkey.id);
      passkeys = passkeys.filter((other) => other.id !== passkey.id);
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    error = "";
    notice = "";
    busy = true;
    const changingLanguage = (language || null) !== (app.me?.language ?? null);
    try {
      app.me = await app.api.updateMe({
        name,
        language: (language || null) as Locale | null,
        current_password: newPassword ? currentPassword : null,
        new_password: newPassword || null,
      });
      if (newPassword) {
        notice = m.password_changed();
        currentPassword = "";
        newPassword = "";
        await loadSessions();
      }
      // The interface follows the account's language, kept on this browser too.
      if (changingLanguage) chooseLanguage((language || null) as Locale | null, reload);
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  async function saveNotifications(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    notifyError = "";
    notifyNotice = "";
    notifyBusy = true;
    try {
      app.me = await app.api.updateMe({
        name: app.me?.name ?? name,
        language: app.me?.language ?? null,
        email,
        phone,
        notify_on: { ...notifyOn },
      });
      email = app.me.email;
      phone = app.me.phone;
      notifyNotice = m.notify_saved();
    } catch (failure) {
      notifyError = errorMessage(failure);
    } finally {
      notifyBusy = false;
    }
  }

  async function sendTest(): Promise<void> {
    notifyError = "";
    notifyNotice = "";
    try {
      const { sent } = await app.api.testNotification();
      if (sent) notifyNotice = m.notify_test_sent();
      else notifyError = m.notify_test_failed();
    } catch (failure) {
      notifyError = errorMessage(failure);
    }
  }

  async function end(session: SessionOut): Promise<void> {
    try {
      await app.api.endSession(session.id);
      sessions = sessions.filter((other) => other.id !== session.id);
    } catch (failure) {
      error = errorMessage(failure);
    }
  }
</script>

<h1>{m.account_title()}</h1>
<form class="card" onsubmit={save}>
  <div class="grid">
    <label>{m.field_name()}<input bind:value={name} required maxlength="100" /></label>
    <label>
      {m.language_label()}
      <select bind:value={language}>
        <option value="">{m.language_browser()}</option>
        {#each locales as locale (locale)}<option value={locale}>{LANGUAGE_NAMES[locale]}</option>{/each}
      </select>
    </label>
  </div>
  <h2>{m.password_title()}</h2>
  <div class="grid">
    <label>
      {m.field_current_password()}
      <input type="password" bind:value={currentPassword} autocomplete="current-password" required={Boolean(newPassword)} />
    </label>
    <label>
      {m.field_new_password()}
      <input type="password" bind:value={newPassword} minlength="10" autocomplete="new-password" />
      <small>{m.field_password_hint()}</small>
    </label>
  </div>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if notice}<p class="note">{notice}</p>{/if}
  <button type="submit" disabled={busy}>{busy ? m.saving() : m.save()}</button>
</form>

{#if channels.length}
  <h2>{m.notify_title()}</h2>
  <form class="card" onsubmit={saveNotifications}>
    <p class="muted">{m.notify_intro()}</p>
    <div class="grid">
      {#if channels.includes("email")}
        <label>{m.field_email()}<input type="email" bind:value={email} maxlength="254" autocomplete="email" /></label>
      {/if}
      {#if channels.includes("signal")}
        <label>
          {m.field_phone()}
          <input type="tel" bind:value={phone} maxlength="30" autocomplete="tel" />
          <small>{m.field_phone_hint({ code: app.me?.phone_country_code ?? "" })}</small>
        </label>
      {/if}
    </div>
    <fieldset>
      <legend>{m.notify_when()}</legend>
      {#each EVENTS as [key, label] (key)}
        <label class="check"><input type="checkbox" bind:checked={notifyOn[key]} /> {label()}</label>
      {/each}
    </fieldset>
    {#if notifyError}<p role="alert">{notifyError}</p>{/if}
    {#if notifyNotice}<p class="note">{notifyNotice}</p>{/if}
    <div class="actions">
      <button type="submit" disabled={notifyBusy}>{notifyBusy ? m.saving() : m.notify_save()}</button>
      {#if app.me?.email || app.me?.phone}
        <button type="button" class="secondary" onclick={sendTest}>{m.notify_test()}</button>
      {/if}
    </div>
  </form>
{/if}

<h2>{m.passkeys_title()}</h2>
<p class="muted">{m.passkeys_intro()}</p>
<ul class="list">
  {#each passkeys as passkey (passkey.id)}
    <li>
      <span class="what">
        <strong>{passkey.label}</strong>
        <small>
          {passkey.last_used_at ? m.session_last_seen({ when: moment(passkey.last_used_at) }) : m.passkey_unused()}
        </small>
      </span>
      <button type="button" class="link" onclick={() => removePasskey(passkey)}>{m.passkey_remove()}</button>
    </li>
  {/each}
</ul>
{#if app.authenticator.supported()}
  <button type="button" class="secondary" onclick={addPasskey}>{m.passkey_add()}</button>
{/if}

<h2>{m.sessions_title()}</h2>
<ul class="list">
  {#each sessions as session (session.id)}
    <li>
      <span class="what">
        <strong>{session.current ? m.session_this() : session.user_agent || "—"}</strong>
        <small>{m.session_last_seen({ when: moment(session.last_seen_at) })}</small>
      </span>
      {#if !session.current}
        <button type="button" class="link" onclick={() => end(session)}>{m.session_end()}</button>
      {/if}
    </li>
  {/each}
</ul>
