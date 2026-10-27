import { fireEvent, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Proposal, Service } from "../lib/api";
import { holdDraft, takeDraft } from "../lib/draft";
import { navigate, route } from "../lib/router.svelte";
import { ELECTRICITY, aBill, appFor, fakeApi, refuse, renderPage } from "../testing";
import BillForm from "./BillForm.svelte";
import Bills from "./Bills.svelte";
import Reports from "./Reports.svelte";

const SERVICE: Service = {
  id: 5, supplier_id: 1, name: "Electricity", identifiers: {}, default_category_id: ELECTRICITY.id,
  starts_on: null, ends_on: "2026-11-30", renews_automatically: true, lock_in_until: null,
  notice_days: 30, billed_every_days: 30, notes: "", active: true, in_use: false,
};

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    supplier_id: 1,
    supplier_name: "MEO Energia",
    issuer_nif: "506743357",
    service_id: SERVICE.id,
    date: "2026-10-18",
    invoice_number: "FT FA.MEA26/100001",
    total_cents: 28759,
    period_start: "2026-09-13",
    period_end: "2026-10-16",
    due_date: "2026-11-03",
    lines: [{ description: "", amount_cents: 28759, category_id: ELECTRICITY.id }],
    readings: [{ quantity: "electricity_kwh", value: 1284, unit_price: 0.1525 }],
    service_changes: { ends_on: "2026-12-11", renews_automatically: false, lock_in_until: "2027-07-28" },
    identifiers: { CPE: "PT0002000099999999ZZ" },
    contract: { ends_on: "2026-12-11", renews_automatically: true, lock_in_until: null, billed_every_days: 30 },
    sources: { total_cents: "qr", on: "qr", period_start: "text" },
    warnings: [],
    text_source: "text",
    duplicate_bill_id: null,
    ...overrides,
  };
}

const file = () => new File(["%PDF"], "bill.pdf", { type: "application/pdf" });

beforeEach(() => {
  history.replaceState(null, "", "/elsewhere");
  navigate("/bills", { replace: true });
});
afterEach(() => {
  takeDraft();
  vi.restoreAllMocks();
});

describe("the hand-over", () => {
  it("gives the read bill once", () => {
    const draft = { proposal: proposal(), file: file() };
    holdDraft(draft);
    expect(takeDraft()).toBe(draft);
    expect(takeDraft()).toBeNull();
  });
});

describe("reading a bill from the list", () => {
  it("reads the file and opens the bill form with it", async () => {
    const { api, calls } = fakeApi({
      "GET /bills": { items: [], total: 0 },
      "GET /reports/summary": refuse(500, "x"),
      "POST /bills/read": proposal(),
    });
    renderPage(Bills, appFor(api));
    const input = (await screen.findByLabelText("Upload a bill")) as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [] } });
    await fireEvent.change(input, { target: { files: [file()] } });

    await waitFor(() => expect(route.path).toBe("/bills/new"));
    expect(calls.some((c) => c.path === "/bills/read")).toBe(true);
    expect(takeDraft()?.proposal.total_cents).toBe(28759);
  });

  it("explains a file that cannot be read", async () => {
    const { api } = fakeApi({ "GET /bills": { items: [], total: 0 }, "GET /reports/summary": refuse(500, "x"), "POST /bills/read": refuse(504, "read_timeout") });
    renderPage(Bills, appFor(api));
    await fireEvent.change(await screen.findByLabelText("Upload a bill"), { target: { files: [file()] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
    expect(route.path).toBe("/bills");
  });
});

describe("a read bill in the form", () => {
  it("opens with what was read, says where it came from, and saves it with its file and service dates", async () => {
    holdDraft({ proposal: proposal(), file: file() });
    const { api, calls } = fakeApi({
      "GET /services": [SERVICE],
      "GET /suppliers": [],
      "POST /bills": aBill({ id: 42 }),
      "POST /attachments": { id: 1, filename: "bill.pdf", content_type: "application/pdf", size: 4 },
      "PUT /services/5": SERVICE,
      "GET /split-preview": { rule_id: 1, shares: [] },
    });
    renderPage(BillForm, appFor(api));

    expect(screen.getByText("Read from bill.pdf. Check every field before saving.")).toBeInTheDocument();
    expect(screen.getByText(/bill's QR code/)).toBeInTheDocument();
    expect(screen.getByLabelText("Date on the bill")).toHaveValue("2026-10-18");
    expect(screen.getByLabelText("Invoice number")).toHaveValue("FT FA.MEA26/100001");
    expect(screen.getByLabelText("Supplier")).toHaveValue("MEO Energia");
    expect(screen.getByLabelText("Amount (€)")).toHaveValue("287.59");
    expect(screen.getByLabelText("Category")).toHaveValue(String(ELECTRICITY.id));
    expect(screen.getByText(/Electricity: 1,284 kWh at €0.1525\/kWh/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Ends or renews on/)).toBeChecked();
    expect(screen.getByLabelText("Does not renew automatically")).toBeChecked();
    await fireEvent.click(screen.getByLabelText(/Minimum term ends/));

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(route.path).toBe("/bills/42"));

    expect((calls.find((c) => c.path === "/bills")!.body as { readings: unknown[] }).readings).toEqual(proposal().readings);
    expect((calls.find((c) => c.path === "/attachments")!.body as FormData).get("bill_id")).toBe("42");
    const update = calls.find((c) => c.method === "PUT")!.body as Record<string, unknown>;
    expect(update).toMatchObject({ ends_on: "2026-12-11", renews_automatically: false, lock_in_until: null, name: "Electricity" });
    expect(update).not.toHaveProperty("id");
  });

  it("warns of a duplicate, a total that disagrees, dropped items, OCR, Claude and an unknown supplier", async () => {
    holdDraft({
      proposal: proposal({
        duplicate_bill_id: 7,
        warnings: ["total_mismatch", "lines_dropped", "claude_failed"],
        text_source: "ocr",
        supplier_id: null,
        supplier_name: null,
        service_id: null,
        sources: { invoice_number: "claude" },
        lines: [],
        readings: [{ quantity: "water_m3", value: 9, unit_price: null }],
        service_changes: { ends_on: null, renews_automatically: null, lock_in_until: null },
      }),
      file: file(),
    });
    const { api } = fakeApi({ "GET /services": [], "GET /suppliers": [] });
    renderPage(BillForm, appFor(api));

    expect(screen.getByRole("link", { name: "View it" })).toHaveAttribute("href", "/bills/7");
    expect(screen.getByText(/differs from the one in the QR code/)).toBeInTheDocument();
    expect(screen.getByText(/did not add up/)).toBeInTheDocument();
    expect(screen.getByText(/read from a scan/)).toBeInTheDocument();
    expect(screen.getByText(/Claude read some of it/)).toBeInTheDocument();
    expect(screen.getByText(/Claude could not read this bill/)).toBeInTheDocument();
    expect(screen.getByText("The supplier with NIF 506743357 is not on file yet. Enter its name above, and saving adds it to your suppliers.")).toBeInTheDocument();
    expect(screen.getByText("Water: 9 m³ at €—/m³")).toBeInTheDocument();
    expect(screen.queryByText(/bill's QR code/)).not.toBeInTheDocument();
    expect(screen.queryByText("Update the service as well")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Amount (€)")).toHaveValue("");
  });

  it("keeps a bill saved when its file or the service update fails, and skips an unknown service", async () => {
    holdDraft({ proposal: proposal({ service_changes: { ends_on: "2026-12-11", renews_automatically: true, lock_in_until: null } }), file: file() });
    const { api, calls } = fakeApi({
      "GET /services": [],
      "GET /suppliers": [],
      "POST /bills": aBill({ id: 43 }),
      "POST /attachments": refuse(415, "unsupported_file"),
    });
    const app = appFor(api);
    renderPage(BillForm, app);
    expect(screen.getByText("Renews automatically")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills/43"));
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    expect(app.flash).toEqual({ text: expect.stringContaining("could not be attached"), problem: true, path: "/bills/43" });
  });

  it("adds the supplier and the service a first bill comes from, and links the bill to it", async () => {
    holdDraft({
      proposal: proposal({ supplier_id: null, supplier_name: "MEO", issuer_nif: "504615947", service_id: null, service_changes: { ends_on: null, renews_automatically: null, lock_in_until: null } }),
      file: file(),
    });
    const { api, calls } = fakeApi({
      "GET /services": [],
      "GET /suppliers": [],
      "POST /bills": aBill({ id: 43 }),
      "POST /attachments": { id: 1, filename: "bill.pdf", content_type: "application/pdf", size: 4, created_at: "2026-10-26T20:00:00Z" },
      "POST /suppliers": { id: 8, name: "MEO", nif: "504615947", default_category_id: ELECTRICITY.id, notes: "", active: true, in_use: false },
      "POST /services": { ...SERVICE, id: 9, supplier_id: 8 },
      "PUT /bills/43": aBill({ id: 43 }),
    });
    const app = appFor(api);
    renderPage(BillForm, app);

    expect(screen.getByText("Saving adds MEO to your suppliers.")).toBeInTheDocument();
    expect(screen.getByLabelText("Also add the service")).toBeChecked();
    expect(screen.getByLabelText("Service name")).toHaveAttribute("placeholder", "Electricity");
    expect(screen.getByText("References: CPE PT0002000099999999ZZ")).toBeInTheDocument();
    expect(screen.getByText("Renews on 11 Dec 2026")).toBeInTheDocument();
    await fireEvent.input(screen.getByLabelText("Service name"), { target: { value: "Internet at the Quinta" } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills/43"));
    expect(calls.map((c) => `${c.method} ${c.path}`).filter((c) => !c.startsWith("GET"))).toEqual([
      "POST /bills",
      "POST /attachments",
      "POST /suppliers",
      "POST /services",
      "PUT /bills/43",
    ]);
    expect(calls.find((c) => c.path === "/suppliers" && c.method === "POST")!.body).toEqual({
      name: "MEO", nif: "504615947", default_category_id: ELECTRICITY.id, notes: "", active: true,
    });
    expect(calls.find((c) => c.path === "/services" && c.method === "POST")!.body).toMatchObject({
      supplier_id: 8,
      name: "Internet at the Quinta",
      identifiers: { CPE: "PT0002000099999999ZZ" },
      ends_on: "2026-12-11",
      renews_automatically: true,
      billed_every_days: 30,
    });
    expect((calls.find((c) => c.method === "PUT")!.body as { service_id: number }).service_id).toBe(9);
    expect(app.flash?.text).toBe("Bill saved.");
  });

  it("adds only the supplier when the service is not wanted, and none when a service is chosen", async () => {
    holdDraft({ proposal: proposal({ supplier_id: null, supplier_name: "MEO", service_id: null }), file: file() });
    const { api, calls } = fakeApi({
      "GET /services": [SERVICE],
      "GET /suppliers": [],
      "POST /bills": aBill({ id: 43 }),
      "POST /attachments": { id: 1, filename: "bill.pdf", content_type: "application/pdf", size: 4, created_at: "2026-10-26T20:00:00Z" },
      "POST /suppliers": { id: 8, name: "MEO", nif: "506743357", default_category_id: null, notes: "", active: true, in_use: false },
    });
    renderPage(BillForm, appFor(api));
    await fireEvent.click(screen.getByLabelText("Also add the service"));
    expect(screen.queryByLabelText("Service name")).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills/43"));
    expect(calls.some((c) => c.path === "/suppliers" && c.method === "POST")).toBe(true);
    expect(calls.some((c) => c.path === "/services" && c.method === "POST")).toBe(false);
  });

  it("offers no new service once one is chosen, and asks for a name the bill does not give", async () => {
    holdDraft({ proposal: proposal({ supplier_id: null, supplier_name: null, service_id: null }), file: file() });
    const { api } = fakeApi({ "GET /services": [SERVICE], "GET /suppliers": [] });
    renderPage(BillForm, appFor(api));

    expect(screen.getByText(/NIF 506743357 is not on file yet. Enter its name above/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Also add the service")).not.toBeInTheDocument();
    await fireEvent.input(screen.getByLabelText("Supplier"), { target: { value: "Águas do Vale" } });
    expect(screen.getByText("Saving adds Águas do Vale to your suppliers.")).toBeInTheDocument();
    expect(screen.getByLabelText("Also add the service")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("option", { name: "Electricity" })).toBeInTheDocument());
    await fireEvent.change(screen.getByRole("combobox", { name: /^Service/ }), { target: { value: String(SERVICE.id) } });
    expect(screen.queryByLabelText("Also add the service")).not.toBeInTheDocument();
  });

  it("keeps the bill when its supplier or service cannot be added, and says so", async () => {
    holdDraft({ proposal: proposal({ supplier_id: null, supplier_name: "MEO", service_id: null }), file: file() });
    const { api } = fakeApi({
      "GET /services": [],
      "GET /suppliers": [],
      "POST /bills": aBill({ id: 43 }),
      "POST /attachments": { id: 1, filename: "bill.pdf", content_type: "application/pdf", size: 4, created_at: "2026-10-26T20:00:00Z" },
      "POST /suppliers": refuse(409, "supplier_exists"),
    });
    const app = appFor(api);
    renderPage(BillForm, app);
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills/43"));
    expect(app.flash).toEqual({ text: expect.stringContaining("supplier or service could not be added"), problem: true, path: "/bills/43" });
  });

  it("keeps a corrected bill's readings", async () => {
    const reading = { quantity: "electricity_kwh" as const, value: 1284, unit_price: 0.1525 };
    const { api, calls } = fakeApi({ "GET /bills/7": aBill({ readings: [reading] }), "PUT /bills/7": aBill(), "GET /services": [], "GET /suppliers": [] });
    const app = appFor(api);
    renderPage(BillForm, app, { id: 7 });
    await screen.findByDisplayValue("MEO Energia");
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(app.flash).toEqual({ text: "Bill saved.", problem: false, path: "/bills" });
    expect((calls.find((c) => c.method === "PUT")!.body as { readings: unknown[] }).readings).toEqual([reading]);
  });
});

describe("consumption in the reports", () => {
  it("charts each quantity's readings", async () => {
    const { api } = fakeApi({
      "GET /reports/summary": { year: 2026, years: [2026], total_cents: 0, shares: [], categories: [], months: [] },
      "GET /readings": [
        { bill_id: 1, date: "2026-10-18", period_start: null, period_end: "2026-10-16", service_id: 5, quantity: "electricity_kwh", value: 1284, unit_price: 0.1525 },
        { bill_id: 2, date: "2026-11-23", period_start: null, period_end: null, service_id: 5, quantity: "electricity_kwh", value: 900, unit_price: null },
        { bill_id: 3, date: "2026-11-02", period_start: null, period_end: null, service_id: 6, quantity: "water_m3", value: 13.5, unit_price: 0.62 },
      ],
    });
    renderPage(Reports, appFor(api));

    expect(await screen.findByRole("heading", { name: "Electricity used" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Water used" })).toBeInTheDocument();
    expect(screen.getByText(/1,284 kWh/)).toBeInTheDocument();
    expect(screen.getByText(/13.5 m³/)).toBeInTheDocument();
  });

  it("leaves it out when there are no readings or they cannot load", async () => {
    const { api } = fakeApi({
      "GET /reports/summary": { year: 2026, years: [2026], total_cents: 0, shares: [], categories: [], months: [] },
      "GET /readings": refuse(500, "boom"),
    });
    renderPage(Reports, appFor(api));
    expect(await screen.findByText("No bills in 2026.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Electricity used" })).not.toBeInTheDocument();
  });
});

