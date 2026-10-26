<script lang="ts">
  // The menu: the everyday pages and "More" for the rest, with an account menu beside them. On a
  // computer it is one centred bar across the top; on a phone the pages become a tab bar at the
  // bottom, where the thumb is, and "More" opens upwards from it. One menu, laid out by CSS.
  import ArrowLeftRight from "@lucide/svelte/icons/arrow-left-right";
  import CalendarCheck from "@lucide/svelte/icons/calendar-check";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import CircleUser from "@lucide/svelte/icons/circle-user";
  import Ellipsis from "@lucide/svelte/icons/ellipsis";
  import FileText from "@lucide/svelte/icons/file-text";
  import History from "@lucide/svelte/icons/history";
  import LogOut from "@lucide/svelte/icons/log-out";
  import Monitor from "@lucide/svelte/icons/monitor";
  import Moon from "@lucide/svelte/icons/moon";
  import Plug from "@lucide/svelte/icons/plug";
  import Receipt from "@lucide/svelte/icons/receipt";
  import Scale from "@lucide/svelte/icons/scale";
  import Settings from "@lucide/svelte/icons/settings";
  import Sun from "@lucide/svelte/icons/sun";
  import User from "@lucide/svelte/icons/user";
  import { useApp } from "./context";
  import { route } from "./router.svelte";
  import { chooseTheme, chosenTheme, type Theme } from "./theme";
  import { m } from "../paraglide/messages.js";

  let { onLogOut }: { onLogOut: () => void } = $props();
  const app = useApp();

  const everyday = $derived([
    { href: "/", label: m.nav_balances(), icon: Scale },
    { href: "/bills", label: m.nav_bills(), icon: Receipt },
    { href: "/settlements", label: m.nav_settlements(), icon: ArrowLeftRight },
    { href: "/reports", label: m.nav_reports(), icon: ChartColumn },
  ]);
  const more = $derived([
    { href: "/services", label: m.nav_services(), icon: Plug },
    { href: "/documents", label: m.nav_documents(), icon: FileText },
    { href: "/activity", label: m.nav_activity(), icon: History },
    ...(app.me?.reconciliation_enabled
      ? [{ href: "/reconciliation", label: m.reconciliations_title(), icon: CalendarCheck }]
      : []),
  ]);

  function current(href: string): boolean {
    return href === "/" ? route.path === "/" : route.path === href || route.path.startsWith(`${href}/`);
  }

  let open = $state<"more" | "account" | null>(null);

  const THEMES = [
    ["auto", m.theme_auto, Monitor],
    ["light", m.theme_light, Sun],
    ["dark", m.theme_dark, Moon],
  ] as const;
  let theme = $state<Theme>(chosenTheme());

  function pick(choice: Theme): void {
    theme = choice;
    chooseTheme(choice);
  }

  // A menu closes when its page opens, on Escape, and on a click anywhere outside it.
  $effect(() => {
    void route.path;
    open = null;
  });

  function toggle(menu: "more" | "account"): void {
    open = open === menu ? null : menu;
  }

  function closeOutside(event: MouseEvent): void {
    if (open && !(event.target as Element | null)?.closest?.("[data-menu]")) open = null;
  }
</script>

<svelte:window onkeydown={(event) => event.key === "Escape" && (open = null)} onclick={closeOutside} />

<header class="bar">
  <div class="bar-inner">
    <a class="brand" href="/">{app.appName}</a>
    <nav class="pages" aria-label={m.nav_main()}>
      {#each everyday as item (item.href)}
        <a href={item.href} aria-current={current(item.href) ? "page" : undefined}><item.icon /><span>{item.label}</span></a>
      {/each}
      <div class="menu more" data-menu>
        <button
          type="button"
          class="menu-button"
          class:current={more.some((item) => current(item.href))}
          aria-expanded={open === "more"}
          aria-controls="more-menu"
          onclick={() => toggle("more")}
        >
          <Ellipsis /><span>{m.nav_more()}</span><ChevronDown class="chevron" />
        </button>
        {#if open === "more"}
          <ul class="menu-panel" id="more-menu">
            {#each more as item (item.href)}
              <li><a href={item.href} aria-current={current(item.href) ? "page" : undefined}><item.icon />{item.label}</a></li>
            {/each}
          </ul>
        {/if}
      </div>
    </nav>
    <div class="menu account" data-menu>
      <button type="button" class="menu-button" aria-expanded={open === "account"} aria-controls="account-menu" onclick={() => toggle("account")}>
        <CircleUser /><span class="name">{app.me?.name}</span><ChevronDown class="chevron" />
      </button>
      {#if open === "account"}
        <ul class="menu-panel" id="account-menu">
          <li><a href="/account" aria-current={current("/account") ? "page" : undefined}><User />{m.nav_account()}</a></li>
          {#if app.isAdmin}
            <li><a href="/admin" aria-current={current("/admin") ? "page" : undefined}><Settings />{m.nav_admin()}</a></li>
          {/if}
          <li class="theme" role="group" aria-label={m.theme_label()}>
            {#each THEMES as [value, label, Icon] (value)}
              <button type="button" aria-pressed={theme === value} aria-label={label()} title={label()} onclick={() => pick(value)}>
                <Icon />
              </button>
            {/each}
          </li>
          <li><button type="button" onclick={onLogOut}><LogOut />{m.nav_log_out()}</button></li>
        </ul>
      {/if}
    </div>
  </div>
</header>
