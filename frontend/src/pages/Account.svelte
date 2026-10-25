<script lang="ts">
  import { onMount } from "svelte";
  import type { SessionOut } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { moment } from "../lib/format";
  import { LANGUAGE_NAMES, chooseLanguage } from "../lib/language";
  import { m } from "../paraglide/messages.js";
  import { locales, type Locale } from "../paraglide/runtime.js";

  let { reload = () => location.reload() }: { reload?: () => void } = $props();
  const app = useApp();

  let name = $state(app.me?.name ?? "");
  let language = $state<string>(app.me?.language ?? "");
  let currentPassword = $state("");
  let newPassword = $state("");
  let sessions = $state<SessionOut[]>([]);
  let error = $state("");
  let notice = $state("");
  let busy = $state(false);

  async function loadSessions(): Promise<void> {
    try {
      sessions = await app.api.sessions();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  onMount(() => {
    loadSessions();
  });

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
