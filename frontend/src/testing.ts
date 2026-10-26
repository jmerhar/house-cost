/**
 * What the tests share: a stand-in API server answering by method and path, and the households,
 * categories and people the agreement's examples use.
 */

import { render } from "@testing-library/svelte";
import type { Component } from "svelte";
import { Api, type Bill, type Category, type Household, type Me, type Person, type Rule } from "./lib/api";
import { contextFor } from "./lib/context";
import type { Authenticator } from "./lib/passkeys";
import { AppState } from "./lib/state.svelte";

export type Call = { method: string; path: string; query: URLSearchParams; body: unknown };
type Answer = object | string | number | boolean | null | undefined;
type Handler = Answer | ((call: Call) => Answer | Promise<Answer>);

/** A response refusing a request, as the API refuses one. */
export function refuse(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * An Api whose requests are answered by ``routes``, keyed "METHOD /path" (the path without /api
 * and without its query). A handler may be a value, a Response, or a function of the call; a
 * route that is missing answers 404, and ``calls`` records every request made.
 */
export function fakeApi(routes: Record<string, Handler>): { api: Api; calls: Call[] } {
  const calls: Call[] = [];
  const fetcher = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input), "http://house-cost.test");
    const method = init?.method ?? "GET";
    let body: unknown = init?.body;
    if (typeof body === "string") body = JSON.parse(body);
    const call: Call = { method, path: url.pathname.replace(/^\/api/, ""), query: url.searchParams, body };
    calls.push(call);
    const handler = routes[`${method} ${call.path}`];
    if (handler === undefined) return refuse(404, "not_found");
    const answer = typeof handler === "function" ? await (handler as (c: Call) => Answer)(call) : handler;
    if (answer instanceof Response) return answer;
    if (answer === undefined) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(answer), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  return { api: new Api("/api", fetcher as typeof fetch), calls };
}

export const LUCIA: Household = { id: 1, name: "Lúcia", position: 0, active: true };
export const OWNERS: Household = { id: 2, name: "Tiago + Marta", position: 1, active: true };
export const HOUSEHOLDS = [LUCIA, OWNERS];

export const ELECTRICITY: Category = { id: 10, name: "Electricity", description: "", active: true };
export const ROAD: Category = { id: 11, name: "Road upkeep", description: "", active: true };
export const CATEGORIES = [ELECTRICITY, ROAD];

export const ADMIN: Me = {
  id: 1,
  name: "Lúcia",
  login: "lucia",
  role: "admin",
  language: null,
  household_id: LUCIA.id,
  active: true,
  household_name: LUCIA.name,
  reconciliation_enabled: false,
  claude_enabled: false,
  apprise_urls: "",
  notify_on: { new_bill: true, price_change: true, contract: true, missing_bill: true },
};
export const MEMBER: Me = { ...ADMIN, id: 2, name: "Tiago", login: "tiago", role: "member", household_id: OWNERS.id, household_name: OWNERS.name };

export const PEOPLE: Person[] = [
  { id: 1, name: "Lúcia", login: "lucia", role: "admin", language: null, household_id: LUCIA.id, active: true },
  { id: 2, name: "Tiago", login: "tiago", role: "member", language: "en", household_id: OWNERS.id, active: true },
];

export const RULES: Rule[] = [
  {
    id: 100,
    category_id: ELECTRICITY.id,
    effective_from: "2026-09-05",
    note: "Agreement of 5 Sep 2026",
    shares: [
      { household_id: LUCIA.id, basis_points: 5000 },
      { household_id: OWNERS.id, basis_points: 5000 },
    ],
    created_at: "2026-09-05T10:00:00Z",
    in_use: true,
  },
  {
    id: 101,
    category_id: ROAD.id,
    effective_from: "2026-09-05",
    note: "",
    shares: [
      { household_id: LUCIA.id, basis_points: 4000 },
      { household_id: OWNERS.id, basis_points: 6000 },
    ],
    created_at: "2026-09-05T10:00:00Z",
    in_use: false,
  },
];

/** A bill: MEO Energia's October invoice, paid by the owners, split evenly. */
export function aBill(overrides: Partial<Bill> = {}): Bill {
  return {
    id: 7,
    date: "2026-10-18",
    supplier: "MEO Energia",
    description: "Electricity",
    invoice_number: "FA MEA26/100001",
    period_start: "2026-09-13",
    period_end: "2026-10-16",
    due_date: "2026-11-03",
    total_cents: 28759,
    paid_by_id: OWNERS.id,
    service_id: null,
    notes: "",
    lines: [
      {
        id: 70,
        description: "",
        category_id: ELECTRICITY.id,
        amount_cents: 28759,
        rule_id: 100,
        shares: [
          { household_id: LUCIA.id, amount_cents: 14380 },
          { household_id: OWNERS.id, amount_cents: 14379 },
        ],
      },
    ],
    attachments: [],
    readings: [],
    created_at: "2026-10-24T09:00:00Z",
    updated_at: "2026-10-24T09:00:00Z",
    locked: false,
    ...overrides,
  };
}

/** An authenticator that answers every ceremony with ``answer``, or fails with ``error``. */
export function fakeAuthenticator(answer: unknown = { id: "credential" }, error?: Error): Authenticator {
  const respond = async () => {
    if (error) throw error;
    return answer;
  };
  return { supported: () => true, register: respond, authenticate: respond };
}

/** The app's state for a logged-in ``me``, with the agreement's households and categories. */
export function appFor(api: Api, me: Me = ADMIN, authenticator?: Authenticator): AppState {
  const app = new AppState(api, authenticator);
  app.me = me;
  app.households = HOUSEHOLDS;
  app.categories = CATEGORIES;
  return app;
}

/** Render a page inside the app's context. */
export function renderPage<Props extends Record<string, unknown>>(
  page: Component<Props>,
  app: AppState,
  props?: Props,
) {
  // Cast once here: testing-library's option types cannot see that a page takes these props.
  return render(page as never, { props: props ?? {}, context: contextFor(app) } as never);
}
