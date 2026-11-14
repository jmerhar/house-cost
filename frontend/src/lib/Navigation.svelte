<script lang="ts">
  // The menu, drawn by jigkit's AppNav: the everyday pages, "More" for the rest, and the account
  // menu with the appearance choice. One bar across the top while it fits; otherwise the pages
  // become a tab bar at the bottom, where the thumb is, and "More" opens upwards from it.
  import { AppNav, type NavItem, type NavSwitch } from "@jmerhar/jigkit/nav/svelte";
  import ArrowLeftRight from "@lucide/svelte/icons/arrow-left-right";
  import CalendarCheck from "@lucide/svelte/icons/calendar-check";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
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

  function current(href: string): boolean {
    return href === "/" ? route.path === "/" : route.path === href || route.path.startsWith(`${href}/`);
  }

  /** A page entry, marked when it is the one shown. */
  const page = (href: string, label: string, icon: NavItem["icon"]): NavItem => ({
    href,
    label,
    icon,
    current: current(href),
  });

  const pages = $derived([
    page("/", m.nav_balances(), Scale),
    page("/bills", m.nav_bills(), Receipt),
    page("/settlements", m.nav_settlements(), ArrowLeftRight),
    page("/reports", m.nav_reports(), ChartColumn),
  ]);
  const more = $derived([
    {
      label: m.nav_more(),
      icon: Ellipsis,
      items: [
        page("/services", m.nav_services(), Plug),
        page("/documents", m.nav_documents(), FileText),
        page("/activity", m.nav_activity(), History),
        ...(app.me?.reconciliation_enabled ? [page("/reconciliation", m.reconciliations_title(), CalendarCheck)] : []),
      ],
    },
  ]);

  let theme = $state<Theme>(chosenTheme());
  const switches = $derived<NavSwitch[]>([
    {
      label: m.theme_label(),
      value: theme,
      options: [
        { value: "auto", label: m.theme_auto(), icon: Monitor },
        { value: "light", label: m.theme_light(), icon: Sun },
        { value: "dark", label: m.theme_dark(), icon: Moon },
      ],
      onchange: (value) => {
        theme = value as Theme;
        chooseTheme(theme);
      },
    },
  ]);
</script>

<AppNav
  brand={app.appName}
  home="/"
  {pages}
  menus={more}
  account={{
    name: app.me?.name ?? "",
    icon: CircleUser,
    items: [
      page("/account", m.nav_account(), User),
      ...(app.isAdmin ? [page("/admin", m.nav_admin(), Settings)] : []),
    ],
    switches,
    logOut: { label: m.nav_log_out(), icon: LogOut, onclick: onLogOut },
  }}
  labels={{ nav: m.nav_main(), more: m.nav_more(), moreIcon: Ellipsis }}
/>
