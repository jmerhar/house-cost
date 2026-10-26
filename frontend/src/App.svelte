<script lang="ts">
  import Flash from "./lib/Flash.svelte";
  import Footer from "./lib/Footer.svelte";
  import PasskeyOffer from "./lib/PasskeyOffer.svelte";
  import { onMount } from "svelte";
  import { Api, ApiError } from "./lib/api";
  import { provideApp } from "./lib/context";
  import { errorMessage } from "./lib/errors";
  import { chooseLanguage, chosenLanguage } from "./lib/language";
  import type { Locale } from "./paraglide/runtime.js";
  import { followHistory, interceptLinks, match, navigate, route } from "./lib/router.svelte";
  import { AppState } from "./lib/state.svelte";
  import { m } from "./paraglide/messages.js";
  import Account from "./pages/Account.svelte";
  import Activity from "./pages/Activity.svelte";
  import Admin from "./pages/Admin.svelte";
  import Balances from "./pages/Balances.svelte";
  import BillForm from "./pages/BillForm.svelte";
  import Bills from "./pages/Bills.svelte";
  import Login from "./pages/Login.svelte";
  import Reconciliations from "./pages/Reconciliations.svelte";
  import Reports from "./pages/Reports.svelte";
  import Documents from "./pages/Documents.svelte";
  import Services from "./pages/Services.svelte";
  import Settlements from "./pages/Settlements.svelte";
  import Setup from "./pages/Setup.svelte";

  let { api = new Api(), reload = () => location.reload() }: { api?: Api; reload?: () => void } = $props();

  // One API for the app's lifetime: the state is built from it once.
  // svelte-ignore state_referenced_locally
  const app = new AppState(api);
  provideApp(app);

  /** What the app is showing before anyone is logged in. */
  let stage = $state<"loading" | "setup" | "login" | "ready" | "error">("loading");
  let problem = $state("");
  let root: HTMLElement;

  async function start(): Promise<void> {
    try {
      if ((await api.setupState()).required) {
        stage = "setup";
        return;
      }
      app.me = await api.me();
      if (followAccountLanguage()) return;
      await app.refresh();
      stage = "ready";
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) stage = "login";
      else {
        problem = errorMessage(error);
        stage = "error";
      }
    }
  }

  /**
   * Switch to the language saved on the account when this browser shows another, so a choice
   * made on one device follows the person to every other. Returns whether a reload is under way.
   */
  function followAccountLanguage(): boolean {
    const wanted = app.me?.language;
    if (!wanted || wanted === chosenLanguage()) return false;
    let reloading = false;
    chooseLanguage(wanted as Locale, () => {
      reloading = true;
      reload();
    });
    return reloading;
  }

  async function loggedIn(): Promise<void> {
    if (followAccountLanguage()) return;
    await app.refresh();
    stage = "ready";
  }

  async function logOut(): Promise<void> {
    await api.logOut();
    app.me = null;
    stage = "login";
    navigate("/", { replace: true });
  }

  onMount(() => {
    const stopHistory = followHistory();
    const stopLinks = interceptLinks(root);
    start();
    return () => {
      stopHistory();
      stopLinks();
    };
  });

  const NAV = $derived([
    { href: "/", label: m.nav_balances() },
    { href: "/bills", label: m.nav_bills() },
    { href: "/settlements", label: m.nav_settlements() },
    { href: "/reports", label: m.nav_reports() },
    { href: "/services", label: m.nav_services() },
    { href: "/documents", label: m.nav_documents() },
    { href: "/activity", label: m.nav_activity() },
    ...(app.isAdmin ? [{ href: "/admin", label: m.nav_admin() }] : []),
    ...(app.me?.reconciliation_enabled ? [{ href: "/reconciliation", label: m.reconciliations_title() }] : []),
    { href: "/account", label: m.nav_account() },
  ]);

  function current(href: string, path: string): boolean {
    return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
  }

  const billId = $derived(match("/bills/:id", route.path)?.id);
</script>

<div class="app" bind:this={root}>
  {#if stage === "loading"}
    <p class="centre">{m.loading()}</p>
  {:else if stage === "error"}
    <p class="centre" role="alert">{problem}</p>
  {:else if stage === "setup"}
    <Setup onDone={loggedIn} />
  {:else if stage === "login"}
    <Login onDone={loggedIn} />
  {:else}
    <header class="bar">
      <a class="brand" href="/">{m.app_name()}</a>
      <nav aria-label={m.app_name()}>
        {#each NAV as item (item.href)}
          <a href={item.href} aria-current={current(item.href, route.path) ? "page" : undefined}>{item.label}</a>
        {/each}
        <button type="button" class="nav-action" onclick={logOut}>{m.nav_log_out()}</button>
      </nav>
    </header>
    <main>
      <PasskeyOffer />
      <Flash />
      {#if route.path === "/"}
        <Balances />
      {:else if route.path === "/bills"}
        <Bills />
      {:else if route.path === "/bills/new"}
        <BillForm />
      {:else if billId}
        {#key billId}
          <BillForm id={Number(billId)} />
        {/key}
      {:else if route.path === "/settlements"}
        <Settlements />
      {:else if route.path === "/reports"}
        <Reports />
      {:else if route.path === "/services"}
        <Services />
      {:else if route.path === "/documents"}
        <Documents />
      {:else if route.path === "/activity"}
        <Activity />
      {:else if route.path === "/account"}
        <Account />
      {:else if route.path === "/admin" && app.isAdmin}
        <Admin />
      {:else if route.path === "/reconciliation" && app.me?.reconciliation_enabled}
        <Reconciliations />
      {:else}
        <p>{m.not_found()}</p>
      {/if}
    </main>
  {/if}
  {#if stage !== "loading"}<Footer />{/if}
</div>
