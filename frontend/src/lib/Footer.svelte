<script lang="ts">
  // The version running, and the commit its image was built from, which says exactly what is
  // installed when that is a build of the main branch rather than a release.
  import { onMount } from "svelte";
  import type { Health } from "./api";
  import { useApp } from "./context";
  import { m } from "../paraglide/messages.js";

  /** Where a commit of the app's source can be read. */
  const COMMITS = "https://github.com/jmerhar/house-cost/commit/";

  const app = useApp();
  let health = $state<Health | null>(null);

  onMount(() => {
    app.api.health().then(
      (found) => (health = found),
      () => {
        // Without it the footer stays empty; the page itself reports a server it cannot reach.
      },
    );
  });
</script>

{#if health}
  <footer>
    {m.app_name()} {health.version}
    {#if health.revision}· <a href={COMMITS + health.revision}>{health.revision.slice(0, 7)}</a>{/if}
  </footer>
{/if}
