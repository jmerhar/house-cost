<script lang="ts">
  import { onMount } from "svelte";
  import { Api, type Health } from "./lib/api";
  import { LANGUAGE_NAMES, chooseLanguage, chosenLanguage } from "./lib/language";
  import { m } from "./paraglide/messages.js";
  import { locales, type Locale } from "./paraglide/runtime.js";

  let { api = new Api(), reload = () => location.reload() }: { api?: Api; reload?: () => void } =
    $props();

  let health = $state<Health | null>(null);
  let unreachable = $state(false);
  let language = $state<Locale | "">(chosenLanguage() ?? "");

  onMount(() => {
    api.health().then(
      (answer) => (health = answer),
      () => (unreachable = true),
    );
  });

  function onLanguage(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    chooseLanguage(value ? (value as Locale) : null, reload);
  }
</script>

<main>
  <header>
    <h1>{m.app_name()}</h1>
    <label>
      <span>{m.language_label()}</span>
      <select value={language} onchange={onLanguage}>
        <option value="">{m.language_browser()}</option>
        {#each locales as locale (locale)}
          <option value={locale}>{LANGUAGE_NAMES[locale]}</option>
        {/each}
      </select>
    </label>
  </header>
  <p class="tagline">{m.app_tagline()}</p>
  <p>{m.coming_soon()}</p>
  <footer>
    {#if health}
      <span>{m.server_version({ version: health.version })}</span>
    {:else if unreachable}
      <span role="alert">{m.server_unreachable()}</span>
    {/if}
  </footer>
</main>
