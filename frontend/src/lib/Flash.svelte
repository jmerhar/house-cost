<script lang="ts">
  // The message an action left for the page it led to, such as "Bill saved.": shown on that page
  // only, and dropped when the person moves to any other.
  import { useApp } from "./context";
  import { route } from "./router.svelte";

  const app = useApp();

  $effect(() => {
    if (app.flash && app.flash.path !== route.path) app.flash = null;
  });
</script>

{#if app.flash?.path === route.path}
  <p class={app.flash.problem ? "note problem" : "note"} role="status">{app.flash.text}</p>
{/if}
