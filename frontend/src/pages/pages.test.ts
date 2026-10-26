import { fireEvent, screen, waitFor, within } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigate } from "../lib/router.svelte";
import {
  ADMIN,
  ELECTRICITY,
  LUCIA,
  MEMBER,
  OWNERS,
  PEOPLE,
  ROAD,
  RULES,
  aBill,
  appFor,
  fakeApi,
  fakeAuthenticator,
  refuse,
  renderPage,
} from "../testing";
import Account from "./Account.svelte";
import Activity from "./Activity.svelte";
import Admin from "./Admin.svelte";
import Balances from "./Balances.svelte";
import Bills from "./Bills.svelte";
import Login from "./Login.svelte";
import Reconciliations from "./Reconciliations.svelte";
import Reports from "./Reports.svelte";
import Settlements from "./Settlements.svelte";
import Setup from "./Setup.svelte";

beforeEach(() => {
  history.replaceState(null, "", "/elsewhere");
  navigate("/", { replace: true });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  localStorage.clear();
});

describe("Setup", () => {
  it("creates the first admin in the browser's chosen language", async () => {
    localStorage.setItem("house-cost-language", "en");
    const onDone = vi.fn();
    const { api, calls } = fakeApi({ "POST /setup": ADMIN });
    const app = appFor(api);
    app.me = null;
    renderPage(Setup, app, { onDone });
    await fireEvent.input(screen.getByLabelText("Your household's name"), { target: { value: "Lúcia" } });
    await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "Lúcia" } });
    await fireEvent.input(screen.getByLabelText("Login"), { target: { value: "lucia" } });
    await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: "correct horse battery" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Set up" }).closest("form")!);

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(app.me).toEqual(ADMIN);
    expect(calls[0].body).toEqual({
      household_name: "Lúcia",
      name: "Lúcia",
      login: "lucia",
      password: "correct horse battery",
      language: "en",
    });
  });

  it("shows why setup was refused", async () => {
    const { api } = fakeApi({ "POST /setup": refuse(409, "already_set_up") });
    renderPage(Setup, appFor(api), { onDone: vi.fn() });
    await fireEvent.submit(screen.getByRole("button", { name: "Set up" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("already been set up");
  });
});

describe("Login", () => {
  it("shows why a login was refused", async () => {
    const { api } = fakeApi({ "POST /auth/login": refuse(401, "invalid_login") });
    renderPage(Login, appFor(api), { onDone: vi.fn() });
    await fireEvent.submit(screen.getByRole("button", { name: "Log in" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("do not match");
  });
});

describe("Balances", () => {
  const balance = (household: typeof LUCIA, cents: number, adjustment = 0) => ({
    household_id: household.id,
    name: household.name,
    paid_cents: 20000,
    share_cents: 15027,
    adjustment_cents: adjustment,
    sent_cents: 5000,
    received_cents: 0,
    balance_cents: cents,
  });

  it("shows who is owed and who owes, and the transfer that settles it", async () => {
    const { api } = fakeApi({
      "GET /balances": {
        households: [balance(LUCIA, 9973), balance(OWNERS, -9973)],
        transfers: [{ from_id: OWNERS.id, to_id: LUCIA.id, amount_cents: 9973 }],
      },
    });
    renderPage(Balances, appFor(api));

    expect(await screen.findByText("is owed €99.73")).toBeInTheDocument();
    expect(screen.getByText("owes €99.73")).toBeInTheDocument();
    expect(screen.getByText("Tiago + Marta pays Lúcia €99.73")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record this transfer" })).toHaveAttribute(
      "href",
      "/settlements?from=2&to=1&amount=9973",
    );
    expect(screen.queryByText("Reconciled")).not.toBeInTheDocument();
  });

  it("shows reconciliation adjustments only when there are some, and says when everyone is square", async () => {
    const { api } = fakeApi({
      "GET /balances": { households: [balance(LUCIA, 0, 300), balance(OWNERS, 0, -300)], transfers: [] },
    });
    renderPage(Balances, appFor(api));

    expect(await screen.findByText("Everyone is square.")).toBeInTheDocument();
    expect(screen.getAllByText("Reconciled")).toHaveLength(2);
    expect(screen.getAllByText("is square")).toHaveLength(2);
  });

  it("says so when the balances cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /balances": refuse(500, "boom") });
    renderPage(Balances, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Bills", () => {
  it("lists bills with their categories, payer and total", async () => {
    const { api } = fakeApi({
      "GET /bills": { items: [aBill(), aBill({ id: 8, supplier: "", description: "", locked: true })], total: 2 },
      "GET /reports/summary": { year: 2026, years: [2026, 2025], total_cents: 0, shares: [], categories: [], months: [] },
    });
    renderPage(Bills, appFor(api));

    expect(await screen.findByText("MEO Energia")).toBeInTheDocument();
    expect(screen.getByText("Bills: 2")).toBeInTheDocument();
    expect(screen.getAllByText("Electricity · paid by Tiago + Marta")).toHaveLength(2);
    expect(screen.getByText("Reconciled")).toBeInTheDocument();
    expect(screen.getAllByRole("link")[1]).toHaveAttribute("href", "/bills/7");
    expect(await screen.findByRole("option", { name: "2025" })).toBeInTheDocument();
  });

  it("narrows the list by year, category, payer and text", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { api, calls } = fakeApi({ "GET /bills": { items: [], total: 0 }, "GET /reports/summary": refuse(500, "x") });
    renderPage(Bills, appFor(api));
    expect(await screen.findByText("No bills yet.")).toBeInTheDocument();

    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ROAD.id) } });
    await fireEvent.change(screen.getByLabelText("Paid by"), { target: { value: String(LUCIA.id) } });
    await fireEvent.input(screen.getByLabelText("Search"), { target: { value: "meo" } });
    vi.advanceTimersByTime(300);

    await waitFor(() => expect(calls.at(-1)!.query.get("q")).toBe("meo"));
    expect(calls.at(-1)!.query.get("category_id")).toBe(String(ROAD.id));
    expect(calls.at(-1)!.query.get("paid_by_id")).toBe(String(LUCIA.id));
    expect(await screen.findByText("No bills match.")).toBeInTheDocument();
  });

  it("shows more on request", async () => {
    const { api, calls } = fakeApi({
      "GET /bills": (call) =>
        call.query.get("offset") === "0" ? { items: [aBill()], total: 2 } : { items: [aBill({ id: 9, supplier: "SMAS" })], total: 2 },
      "GET /reports/summary": { year: 2026, years: [], total_cents: 0, shares: [], categories: [], months: [] },
    });
    renderPage(Bills, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Show more" }));

    expect(await screen.findByText("SMAS")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/bills").at(-1)!.query.get("offset")).toBe("1");
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("says so when the list cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /bills": refuse(500, "boom") });
    renderPage(Bills, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Settlements", () => {
  const transfer = {
    id: 3,
    date: "2026-11-01",
    from_id: OWNERS.id,
    to_id: LUCIA.id,
    amount_cents: 9973,
    note: "MB Way",
    attachments: [{ id: 4, filename: "receipt.png", content_type: "image/png", size: 100 }],
    created_at: "2026-11-01T10:00:00Z",
  };

  it("lists transfers and records a new one", async () => {
    const { api, calls } = fakeApi({ "GET /settlements": [transfer], "POST /settlements": transfer });
    renderPage(Settlements, appFor(api, MEMBER));

    expect(await screen.findByText("Tiago + Marta paid Lúcia")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "receipt.png" })).toHaveAttribute("href", "/api/attachments/4");
    await fireEvent.click(screen.getByRole("button", { name: "Record a transfer" }));
    expect(screen.getByLabelText("From")).toHaveValue(String(OWNERS.id));
    await fireEvent.change(screen.getByLabelText("To"), { target: { value: String(LUCIA.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "99,73" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      from_id: OWNERS.id,
      to_id: LUCIA.id,
      amount_cents: 9973,
    });
  });

  it("opens filled in from a suggested transfer", async () => {
    history.replaceState(null, "", "/settlements?from=2&to=1&amount=9973");
    const { api } = fakeApi({ "GET /settlements": [] });
    renderPage(Settlements, appFor(api));

    expect(await screen.findByLabelText("Amount (€)")).toHaveValue("99.73");
    expect(screen.getByLabelText("From")).toHaveValue("2");
    expect(screen.getByLabelText("To")).toHaveValue("1");
    expect(await screen.findByText("No transfers recorded yet.")).toBeInTheDocument();
  });

  it("corrects and deletes a transfer", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi({
      "GET /settlements": [transfer],
      "PUT /settlements/3": transfer,
      "DELETE /settlements/3": () => undefined,
    });
    renderPage(Settlements, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getByRole("heading", { name: "Edit transfer" })).toBeInTheDocument();
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));

    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("refuses an amount that is not positive, and shows the API's refusals", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi({
      "GET /settlements": [transfer],
      "PUT /settlements/3": refuse(422, "invalid"),
      "DELETE /settlements/3": refuse(500, "boom"),
    });
    renderPage(Settlements, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "0" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter an amount");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);

    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "5" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Some fields are not valid.");
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("heading", { name: "Edit transfer" })).not.toBeInTheDocument();
  });

  it("attaches a receipt to a transfer", async () => {
    const { api } = fakeApi({
      "GET /settlements": [{ ...transfer, attachments: [] }],
      "POST /attachments": (call) =>
        (call.body as FormData).get("settlement_id") === "3"
          ? { id: 6, filename: "proof.pdf", content_type: "application/pdf", size: 10 }
          : refuse(422, "one_owner"),
    });
    renderPage(Settlements, appFor(api));
    const input = (await screen.findByLabelText("Attach a PDF or a photo")) as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [new File(["%PDF"], "proof.pdf")] } });

    expect(await screen.findByRole("link", { name: "proof.pdf" })).toBeInTheDocument();
  });

  it("reports a receipt that cannot be attached", async () => {
    const { api } = fakeApi({ "GET /settlements": [{ ...transfer, attachments: [] }], "POST /attachments": refuse(413, "too_large") });
    renderPage(Settlements, appFor(api));
    const input = (await screen.findByLabelText("Attach a PDF or a photo")) as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [] } });
    await fireEvent.change(input, { target: { files: [new File(["x"], "big.pdf")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("too large");
  });

  it("says so when the list cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /settlements": refuse(500, "boom") });
    renderPage(Settlements, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Reports", () => {
  const summary = (year: number) => ({
    year,
    years: [2027, 2026],
    total_cents: 57323,
    shares: [
      { household_id: LUCIA.id, amount_cents: 24000 },
      { household_id: OWNERS.id, amount_cents: 33323 },
    ],
    categories: [
      {
        category_id: ELECTRICITY.id,
        name: "Electricity",
        total_cents: 43813,
        shares: [
          { household_id: LUCIA.id, amount_cents: 23662 },
          { household_id: OWNERS.id, amount_cents: 23661 },
        ],
      },
    ],
    months: [
      { month: 10, total_cents: 25054, shares: [] },
      { month: 11, total_cents: 28759, shares: [] },
    ],
  });

  it("shows a year by category and by month, and offers its CSV", async () => {
    const { api, calls } = fakeApi({ "GET /reports/summary": (call) => summary(Number(call.query.get("year") || 2027)) });
    renderPage(Reports, appFor(api));

    expect(await screen.findByRole("heading", { name: "By category · 2027" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Electricity" })).toBeInTheDocument();
    expect(screen.getByText("€573.23")).toBeInTheDocument();
    expect(screen.getByText("October")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download as CSV" })).toHaveAttribute("href", "/api/reports/bills.csv?year=2027");

    await fireEvent.change(screen.getByLabelText("Year"), { target: { value: "2026" } });
    expect(await screen.findByRole("heading", { name: "By category · 2026" })).toBeInTheDocument();
    expect(calls.at(-1)!.query.get("year")).toBe("2026");
  });

  it("says when a year has no bills", async () => {
    const { api } = fakeApi({
      "GET /reports/summary": { year: 2026, years: [], total_cents: 0, shares: [], categories: [], months: [] },
    });
    renderPage(Reports, appFor(api));
    expect(await screen.findByText("No bills in 2026.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Year")).not.toBeInTheDocument();
  });

  it("says so when the report cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /reports/summary": refuse(500, "boom") });
    renderPage(Reports, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Activity", () => {
  const entry = (id: number, overrides: Record<string, unknown> = {}) => ({
    id,
    at: "2026-10-24T09:00:00Z",
    person_id: 2,
    person_name: "Tiago",
    action: "create",
    entity: "bill",
    entity_id: 7,
    before: null,
    after: { supplier: "MEO Energia", total_cents: 28759 },
    ...overrides,
  });

  it("says who did what to which record, linking to bills", async () => {
    const { api } = fakeApi({
      "GET /audit": {
        items: [
          entry(1),
          entry(2, { action: "delete", before: { supplier: "EDP" }, after: null }),
          entry(3, { person_name: null, action: "frobnicate", entity: "widget", after: null }),
        ],
        total: 3,
      },
    });
    renderPage(Activity, appFor(api));

    const first = (await screen.findAllByRole("listitem"))[0];
    expect(first).toHaveTextContent("Tiago added a bill");
    expect(within(first).getByRole("link", { name: "a bill" })).toHaveAttribute("href", "/bills/7");
    expect(first).toHaveTextContent("MEO Energia · €287.59");
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent("Tiago deleted a bill");
    expect(screen.getAllByRole("listitem")[2]).toHaveTextContent("Someone frobnicate widget");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("shows more on request, and says when nothing has happened", async () => {
    const { api } = fakeApi({
      "GET /audit": (call) => (call.query.get("offset") === "0" ? { items: [entry(1)], total: 2 } : { items: [entry(2)], total: 2 }),
    });
    renderPage(Activity, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));

    const empty = fakeApi({ "GET /audit": { items: [], total: 0 } });
    renderPage(Activity, appFor(empty.api));
    expect(await screen.findByText("Nothing has happened yet.")).toBeInTheDocument();
  });

  it("says so when the log cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /audit": refuse(500, "boom") });
    renderPage(Activity, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Account", () => {
  const sessions = [
    { id: 1, created_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-26T10:00:00Z", user_agent: "Firefox", current: true },
    { id: 2, created_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-20T10:00:00Z", user_agent: "Safari on iPhone", current: false },
  ];

  it("changes the name and password, and logs another browser out", async () => {
    const { api, calls } = fakeApi({
      "GET /auth/sessions": sessions,
      "GET /auth/passkeys": [],
      "PATCH /auth/me": (call) => ({ ...ADMIN, name: (call.body as { name: string }).name }),
      "DELETE /auth/sessions/2": () => undefined,
    });
    const app = appFor(api);
    renderPage(Account, app);

    expect(await screen.findByText("This browser")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Log out there" }));
    await waitFor(() => expect(screen.queryByText("Safari on iPhone")).not.toBeInTheDocument());

    await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "Lúcia M." } });
    await fireEvent.input(screen.getByLabelText("Current password"), { target: { value: "old password!" } });
    await fireEvent.input(screen.getByLabelText(/^New password/), { target: { value: "a brand new password" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
    expect(app.me?.name).toBe("Lúcia M.");
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({
      name: "Lúcia M.",
      language: null,
      current_password: "old password!",
      new_password: "a brand new password",
    });
  });

  it("saves a new language and reloads into it", async () => {
    const reload = vi.fn();
    const { api, calls } = fakeApi({ "GET /auth/sessions": [],
      "GET /auth/passkeys": [], "PATCH /auth/me": { ...ADMIN, language: "pt-PT" } });
    renderPage(Account, appFor(api), { reload });
    await fireEvent.change(screen.getByLabelText("Language"), { target: { value: "pt-PT" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ language: "pt-PT", new_password: null });
  });

  it("shows refusals", async () => {
    const { api } = fakeApi({
      "GET /auth/sessions": refuse(500, "boom"),
      "GET /auth/passkeys": [],
      "PATCH /auth/me": refuse(400, "wrong_password"),
      "DELETE /auth/sessions/2": refuse(404, "not_found"),
    });
    renderPage(Account, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("current password is not right");
  });

  it("shows a session that could not be ended", async () => {
    const { api } = fakeApi({ "GET /auth/sessions": sessions,
      "GET /auth/passkeys": [], "DELETE /auth/sessions/2": refuse(404, "not_found") });
    renderPage(Account, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Log out there" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not_found");
  });
});

describe("Admin", () => {
  function adminApi(extra: Parameters<typeof fakeApi>[0] = {}) {
    return fakeApi({
      "GET /people": PEOPLE,
      "GET /rules": RULES,
      "GET /households": [LUCIA, OWNERS],
      "GET /categories": [ELECTRICITY, ROAD],
      ...extra,
    });
  }

  it("lists households, people and each category's rules", async () => {
    const { api } = adminApi();
    renderPage(Admin, appFor(api));

    expect(await screen.findByText("tiago · Tiago + Marta · Member")).toBeInTheDocument();
    expect(screen.getAllByText(/^From 5 Sept? 2026$/)).toHaveLength(2);
    expect(screen.getAllByText("Lúcia 50% · Tiago + Marta 50%")).toHaveLength(1);
    expect(screen.getByText("Lúcia 40% · Tiago + Marta 60%")).toBeInTheDocument();
    expect(screen.getByText("In use")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete rule" })).toBeInTheDocument();
  });

  it("adds, renames, reorders and deactivates households", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("Lúcia S.");
    const { api, calls } = adminApi({
      "POST /households": { id: 3, name: "Third", position: 2, active: true },
      "PUT /households/1": LUCIA,
      "PUT /households/2": OWNERS,
    });
    renderPage(Admin, appFor(api));
    await screen.findByText("tiago · Tiago + Marta · Member");

    await fireEvent.input(screen.getByLabelText("Add a household"), { target: { value: "Third" } });
    await fireEvent.submit(screen.getByLabelText("Add a household").closest("form")!);
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Third", position: 2, active: true }));

    await fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    await waitFor(() => expect(calls.find((c) => c.path === "/households/1")?.body).toMatchObject({ name: "Lúcia S." }));
    await fireEvent.click(screen.getByRole("button", { name: "↑ Tiago + Marta" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/households/2")?.body).toMatchObject({ position: -1 }));
    await fireEvent.click(screen.getAllByRole("button", { name: "Inactive" })[0]);
    await waitFor(() => expect(calls.filter((c) => c.path === "/households/1").at(-1)?.body).toMatchObject({ active: false }));
  });

  it("adds and edits people", async () => {
    const { api, calls } = adminApi({ "POST /people": PEOPLE[1], "PUT /people/2": PEOPLE[1] });
    renderPage(Admin, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Add a person" }));
    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    await fireEvent.input(within(form).getByLabelText("Name"), { target: { value: "Marta" } });
    await fireEvent.input(within(form).getByLabelText("Login"), { target: { value: "marta" } });
    await fireEvent.change(within(form).getByLabelText("Household"), { target: { value: String(OWNERS.id) } });
    await fireEvent.input(within(form).getByLabelText("Password"), { target: { value: "first password" } });
    await fireEvent.submit(form);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        name: "Marta",
        login: "marta",
        role: "member",
        language: null,
        household_id: OWNERS.id,
        password: "first password",
      }),
    );

    await fireEvent.click(screen.getAllByRole("button", { name: "Edit" }).at(-1)!);
    const edit = screen.getByRole("button", { name: "Save" }).closest("form")!;
    await fireEvent.click(within(edit).getByLabelText("Active"));
    await fireEvent.submit(edit);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ active: false, password: null }));
  });

  it("adds a category and a rule from a date, and deletes an unused rule", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = adminApi({
      "POST /categories": { id: 12, name: "Internet", description: "", active: true },
      "PUT /categories/11": ROAD,
      "POST /rules": RULES[1],
      "DELETE /rules/101": () => undefined,
    });
    renderPage(Admin, appFor(api));
    await screen.findByText("tiago · Tiago + Marta · Member");

    await fireEvent.input(screen.getByLabelText("Add a category"), { target: { value: "Internet" } });
    await fireEvent.submit(screen.getByLabelText("Add a category").closest("form")!);
    await waitFor(() => expect(calls.find((c) => c.path === "/categories" && c.method === "POST")).toBeTruthy());

    const road = screen.getByRole("heading", { name: "Road upkeep" }).closest("article")!;
    await fireEvent.click(within(road).getByRole("button", { name: "New rule" }));
    expect(within(road).getByLabelText("Lúcia (%)")).toHaveValue("40");
    await fireEvent.input(within(road).getByLabelText("Lúcia (%)"), { target: { value: "30" } });
    expect(within(road).getByText("Total 90%")).toHaveClass("problem");
    await fireEvent.submit(within(road).getByRole("button", { name: "Save" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("must add up to 100%");

    await fireEvent.input(within(road).getByLabelText("Tiago + Marta (%)"), { target: { value: "70" } });
    await fireEvent.input(within(road).getByLabelText(/Note/), { target: { value: "Amendment" } });
    await fireEvent.submit(within(road).getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/rules" && c.method === "POST")?.body).toMatchObject({
        category_id: ROAD.id,
        note: "Amendment",
        shares: [
          { household_id: LUCIA.id, basis_points: 3000 },
          { household_id: OWNERS.id, basis_points: 7000 },
        ],
      }),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Delete rule" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/rules/101")).toBe(true));
    await fireEvent.click(within(road).getByRole("button", { name: "Inactive" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/categories/11")?.body).toMatchObject({ active: false }));
  });

  it("starts a rule for a category without one at zero, and can cancel it", async () => {
    const { api } = adminApi({ "GET /rules": [] });
    renderPage(Admin, appFor(api));
    const road = (await screen.findByRole("heading", { name: "Road upkeep" })).closest("article")!;
    expect(within(road).getByText(/No rule yet/)).toBeInTheDocument();
    await fireEvent.click(within(road).getByRole("button", { name: "New rule" }));
    expect(within(road).getByLabelText("Lúcia (%)")).toHaveValue("0");
    await fireEvent.click(within(road).getByRole("button", { name: "Cancel" }));
    expect(within(road).queryByLabelText("Lúcia (%)")).not.toBeInTheDocument();
  });

  it("switches reconciliation on and off", async () => {
    const { api, calls } = adminApi({ "PUT /settings": (call) => call.body });
    const app = appFor(api);
    renderPage(Admin, app);
    await fireEvent.click(await screen.findByLabelText("Annual reconciliation"));

    await waitFor(() => expect(app.me?.reconciliation_enabled).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ reconciliation_enabled: true });
  });

  it("shows refusals, such as the last admin stepping down", async () => {
    const { api } = adminApi({ "PUT /people/1": refuse(409, "last_admin"), "POST /households": refuse(409, "name_taken") });
    renderPage(Admin, appFor(api));
    await screen.findByText("tiago · Tiago + Marta · Member");
    await fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[2]);
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[2]);
    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    await fireEvent.change(within(form).getByLabelText("Role"), { target: { value: "member" } });
    await fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("at least one active administrator");

    await fireEvent.input(screen.getByLabelText("Add a household"), { target: { value: "Lúcia" } });
    await fireEvent.submit(screen.getByLabelText("Add a household").closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("already used");
  });

  it("leaves a household as it was when the rename is cancelled", async () => {
    vi.spyOn(window, "prompt").mockReturnValue(null);
    const { api, calls } = adminApi();
    renderPage(Admin, appFor(api));
    await fireEvent.click((await screen.findAllByRole("button", { name: "Edit" }))[0]);
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("says so when it cannot load", async () => {
    const { api } = fakeApi({ "GET /people": refuse(500, "boom"), "GET /rules": [] });
    renderPage(Admin, appFor(api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Reconciliations", () => {
  const draft = {
    id: 1,
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    status: "draft" as const,
    note: "Kiln winter",
    shares: [
      { category_id: ELECTRICITY.id, household_id: LUCIA.id, basis_points: 6000 },
      { category_id: ELECTRICITY.id, household_id: OWNERS.id, basis_points: 4000 },
    ],
    closed_at: null,
    lines: [
      { household_id: LUCIA.id, charged_cents: 15001, reconciled_cents: 18001, adjustment_cents: 3000 },
      { household_id: OWNERS.id, charged_cents: 15000, reconciled_cents: 12000, adjustment_cents: -3000 },
    ],
    bill_count: 2,
  };

  it("shows each household's position and closes a draft after confirming", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi({
      "GET /reconciliations": [draft],
      "POST /reconciliations/1/close": { ...draft, status: "closed" },
    });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));

    expect(await screen.findByText("Kiln winter")).toBeInTheDocument();
    expect(screen.getByText("Bills affected: 2")).toBeInTheDocument();
    expect(screen.getByText("€30.00")).toBeInTheDocument();
    expect(screen.getByText("-€30.00")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Close and write the adjustments" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/reconciliations/1/close")).toBe(true));
  });

  it("creates a draft from the shares typed per category", async () => {
    const { api, calls } = fakeApi({ "GET /reconciliations": [], "POST /reconciliations": draft });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));
    expect(await screen.findByText("No reconciliations yet.")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Reconcile a period" }));
    await fireEvent.input(screen.getByLabelText("Electricity · Lúcia"), { target: { value: "60" } });
    await fireEvent.input(screen.getByLabelText("Electricity · Tiago + Marta"), { target: { value: "40" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect((calls.find((c) => c.method === "POST")!.body as { shares: unknown[] }).shares).toEqual([
      { category_id: ELECTRICITY.id, household_id: LUCIA.id, basis_points: 6000 },
      { category_id: ELECTRICITY.id, household_id: OWNERS.id, basis_points: 4000 },
    ]);
  });

  it("refuses shares that do not add up, and edits and discards a draft", async () => {
    const { api, calls } = fakeApi({
      "GET /reconciliations": [draft],
      "PUT /reconciliations/1": draft,
      "DELETE /reconciliations/1": () => undefined,
    });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));
    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Electricity · Lúcia")).toHaveValue("60");
    await fireEvent.input(screen.getByLabelText("Electricity · Lúcia"), { target: { value: "70" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("Electricity: The shares must add up to 100%.");

    await fireEvent.input(screen.getByLabelText("Electricity · Lúcia"), { target: { value: "60" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("lets members look without changing anything", async () => {
    const { api } = fakeApi({ "GET /reconciliations": [{ ...draft, status: "closed" }] });
    renderPage(Reconciliations, appFor(api, { ...MEMBER, reconciliation_enabled: true }));

    expect(await screen.findByText("Closed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reconcile a period" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("shows refusals", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api } = fakeApi({
      "GET /reconciliations": [draft],
      "POST /reconciliations/1/close": refuse(409, "overlaps_closed_period"),
      "PUT /reconciliations/1": refuse(409, "already_closed"),
      "DELETE /reconciliations/1": refuse(409, "already_closed"),
    });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));
    await fireEvent.click(await screen.findByRole("button", { name: "Close and write the adjustments" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("overlaps one already reconciled");

    await fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("This reconciliation is closed.");
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("says so when the list cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /reconciliations": refuse(500, "boom") });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("does not close without confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { api, calls } = fakeApi({ "GET /reconciliations": [draft] });
    renderPage(Reconciliations, appFor(api, { ...ADMIN, reconciliation_enabled: true }));
    await fireEvent.click(await screen.findByRole("button", { name: "Close and write the adjustments" }));
    expect(calls.some((c) => c.path.endsWith("/close"))).toBe(false);
  });
});

describe("Passkeys", () => {
  const passkey = { id: 9, label: "iPhone", created_at: "2026-10-26T10:00:00Z", last_used_at: null };
  const cancelled = Object.assign(new Error("cancelled"), { name: "NotAllowedError" });

  it("log in from the login page", async () => {
    const onDone = vi.fn();
    const { api, calls } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" }, "POST /auth/passkey-login": MEMBER });
    const app = appFor(api, ADMIN, fakeAuthenticator({ signed: "c" }));
    renderPage(Login, app, { onDone });
    await fireEvent.click(screen.getByRole("button", { name: "Log in with a passkey" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(app.me).toEqual(MEMBER);
    expect(calls.at(-1)!.body).toEqual({ credential: { signed: "c" } });
  });

  it("say nothing when the person cancels, and explain a refusal", async () => {
    const { api } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" }, "POST /auth/passkey-login": refuse(401, "passkey_unknown") });
    renderPage(Login, appFor(api, ADMIN, fakeAuthenticator(undefined, cancelled)), { onDone: vi.fn() });
    await fireEvent.click(screen.getByRole("button", { name: "Log in with a passkey" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in with a passkey" })).toBeEnabled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explain a passkey the server refuses", async () => {
    const { api } = fakeApi({ "POST /auth/passkey-login/options": { challenge: "c" }, "POST /auth/passkey-login": refuse(401, "passkey_unknown") });
    renderPage(Login, appFor(api, ADMIN, fakeAuthenticator()), { onDone: vi.fn() });
    await fireEvent.click(screen.getByRole("button", { name: "Log in with a passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not linked to any account");
  });

  it("are not offered where the browser has none", () => {
    const { api } = fakeApi({});
    renderPage(Login, appFor(api, ADMIN, { ...fakeAuthenticator(), supported: () => false }), { onDone: vi.fn() });
    expect(screen.queryByRole("button", { name: "Log in with a passkey" })).not.toBeInTheDocument();
  });

  it("are added, named and removed on the account page", async () => {
    vi.spyOn(window, "prompt").mockReturnValue(" Phone ");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi({
      "GET /auth/sessions": [],
      "GET /auth/passkeys": [],
      "POST /auth/passkeys/options": { challenge: "c" },
      "POST /auth/passkeys": (call) => ({ ...passkey, label: (call.body as { label: string }).label }),
      "DELETE /auth/passkeys/9": () => undefined,
    });
    renderPage(Account, appFor(api, ADMIN, fakeAuthenticator({ made: "c" })));
    await fireEvent.click(await screen.findByRole("button", { name: "Add a passkey on this device" }));

    expect(await screen.findByText("Phone")).toBeInTheDocument();
    expect(screen.getByText("Not used yet")).toBeInTheDocument();
    expect(screen.getByText(/Passkey added/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/auth/passkeys" && c.method === "POST")!.body).toEqual({ label: "Phone", credential: { made: "c" } });

    await fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(screen.queryByText("Phone")).not.toBeInTheDocument());
  });

  it("are named after the device when the name is left out, and show when they were used", async () => {
    vi.spyOn(window, "prompt").mockReturnValue(null);
    const { api, calls } = fakeApi({
      "GET /auth/sessions": [],
      "GET /auth/passkeys": [{ ...passkey, id: 8, label: "Mac", last_used_at: "2026-10-25T10:00:00Z" }],
      "POST /auth/passkeys/options": { challenge: "c" },
      "POST /auth/passkeys": passkey,
    });
    renderPage(Account, appFor(api, ADMIN, fakeAuthenticator()));
    expect(await screen.findByText(/^Last used/)).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Add a passkey on this device" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/auth/passkeys")).toBe(true));
    expect((calls.find((c) => c.method === "POST" && c.path === "/auth/passkeys")!.body as { label: string }).label).not.toBe("");
  });

  it("report what goes wrong on the account page", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api } = fakeApi({
      "GET /auth/sessions": [],
      "GET /auth/passkeys": [passkey],
      "POST /auth/passkeys/options": refuse(500, "boom"),
      "DELETE /auth/passkeys/9": refuse(404, "not_found"),
    });
    renderPage(Account, appFor(api, ADMIN, fakeAuthenticator()));
    await fireEvent.click(await screen.findByRole("button", { name: "Add a passkey on this device" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not_found");
  });

  it("stay put when removing is not confirmed, a cancelled ceremony says nothing, and a list that fails to load is reported", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { api, calls } = fakeApi({ "GET /auth/sessions": [], "GET /auth/passkeys": [passkey], "POST /auth/passkeys/options": { challenge: "c" } });
    renderPage(Account, appFor(api, ADMIN, fakeAuthenticator(undefined, cancelled)));
    await fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await fireEvent.click(screen.getByRole("button", { name: "Add a passkey on this device" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/auth/passkeys/options")).toBe(true));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("report a list that cannot load", async () => {
    const { api } = fakeApi({ "GET /auth/sessions": [], "GET /auth/passkeys": refuse(500, "boom") });
    renderPage(Account, appFor(api, ADMIN, fakeAuthenticator()));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});
