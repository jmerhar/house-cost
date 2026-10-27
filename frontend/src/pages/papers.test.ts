import { fireEvent, screen, waitFor, within } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentMatch, Service, Supplier } from "../lib/api";
import { navigate } from "../lib/router.svelte";
import { ADMIN, ELECTRICITY, ROAD, aBill, appFor, fakeApi, refuse, renderPage } from "../testing";
import BillForm from "./BillForm.svelte";
import Documents from "./Documents.svelte";
import Services from "./Services.svelte";

const MEO: Supplier = { id: 1, name: "MEO Energia", nif: "506743357", default_category_id: ELECTRICITY.id, notes: "", active: true };
const SMAS: Supplier = { id: 2, name: "SMAS", nif: null, default_category_id: null, notes: "", active: false };
const POWER: Service = {
  id: 5,
  supplier_id: MEO.id,
  name: "Electricity at the Quinta",
  identifiers: { CPE: "PT0002000000000000XX" },
  default_category_id: ELECTRICITY.id,
  starts_on: "2026-09-13",
  ends_on: "2026-11-15",
  renews_automatically: true,
  lock_in_until: "2027-07-28",
  notice_days: 30,
  billed_every_days: 30,
  notes: "",
  active: true,
};
const CONTRACT: DocumentMatch = {
  id: 9,
  title: "MEO Energia contract",
  kind: "contract",
  dated: "2026-09-05",
  supplier_id: MEO.id,
  service_id: POWER.id,
  notes: "",
  filename: "contract.pdf",
  content_type: "application/pdf",
  size: 88_000,
  pages: 2,
  has_text: true,
  created_at: "2026-10-26T10:00:00Z",
  excerpt: "",
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true, now: new Date("2026-10-26T12:00:00Z") });
  history.replaceState(null, "", "/elsewhere");
  navigate("/", { replace: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Services", () => {
  it("lists suppliers with their services, flagging what ends soon", async () => {
    const { api } = fakeApi({ "GET /suppliers": [MEO, SMAS], "GET /services": [POWER, { ...POWER, id: 6, name: "Old line", ends_on: "2030-01-01", lock_in_until: null, notice_days: null, renews_automatically: false, active: false }] });
    renderPage(Services, appFor(api));

    expect(await screen.findByRole("heading", { name: "MEO Energia" })).toBeInTheDocument();
    expect(document.querySelector(".caption")?.textContent?.replace(/\s+/g, " ").trim()).toBe("Supplier · NIF 506743357");
    expect(screen.getAllByRole("heading", { name: "Services", level: 3 }).length).toBeGreaterThan(0);
    expect(screen.getByText("No services yet.")).toBeInTheDocument();
    expect(screen.getAllByText("CPE: PT0002000000000000XX")).toHaveLength(2);
    expect(screen.getByText(/^Renews on 15 Nov 2026$/)).toHaveClass("problem");
    expect(screen.getByText(/^Minimum term ends 28 Jul 2027$/)).not.toHaveClass("problem");
    expect(screen.getByText("Notice (days): 30")).toBeInTheDocument();
    expect(screen.getByText(/^Ends on 1 Jan 2030$/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Documents" })[0]).toHaveAttribute("href", "/documents?service=5");
    expect(screen.getAllByText("Inactive")).toHaveLength(2);
  });

  it("adds a supplier and a service with its references", async () => {
    const { api, calls } = fakeApi({ "GET /suppliers": [MEO], "GET /services": [], "POST /suppliers": SMAS, "POST /services": POWER });
    renderPage(Services, appFor(api));
    await screen.findByRole("heading", { name: "MEO Energia" });

    await fireEvent.click(screen.getByRole("button", { name: "Add a supplier" }));
    await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "SMAS" } });
    await fireEvent.input(screen.getByLabelText("NIF (tax number)"), { target: { value: "" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/suppliers")?.body).toEqual({
      name: "SMAS", nif: null, default_category_id: null, notes: "", active: true,
    }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());

    await fireEvent.click(screen.getByRole("button", { name: "Add a service" }));
    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    expect(within(form).getByLabelText("Usual category")).toHaveValue(String(ELECTRICITY.id));
    await fireEvent.input(within(form).getByLabelText("Name"), { target: { value: "Electricity" } });
    await fireEvent.input(within(form).getByLabelText(/References/), { target: { value: "CPE: PT0002\nno colon here\nCliente: 123" } });
    await fireEvent.input(within(form).getByLabelText("Ends or renews on"), { target: { value: "2026-12-11" } });
    await fireEvent.input(within(form).getByLabelText("Notice (days)"), { target: { value: "30" } });
    await fireEvent.input(within(form).getByLabelText("Billed every (days)"), { target: { value: "30" } });
    await fireEvent.submit(form);

    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/services")?.body).toMatchObject({
      supplier_id: MEO.id,
      name: "Electricity",
      identifiers: { CPE: "PT0002", Cliente: "123" },
      default_category_id: ELECTRICITY.id,
      ends_on: "2026-12-11",
      notice_days: 30,
      billed_every_days: 30,
      lock_in_until: null,
    }));
  });

  it("edits a supplier and a service", async () => {
    const { api, calls } = fakeApi({ "GET /suppliers": [MEO], "GET /services": [POWER], "PUT /suppliers/1": MEO, "PUT /services/5": POWER });
    renderPage(Services, appFor(api));
    await screen.findByText("CPE: PT0002000000000000XX");

    const edits = screen.getAllByRole("button", { name: "Edit" });
    await fireEvent.click(edits[0]);
    const supplierForm = screen.getByRole("button", { name: "Save" }).closest("form")!;
    expect(within(supplierForm).getByLabelText("NIF (tax number)")).toHaveValue("506743357");
    await fireEvent.click(within(supplierForm).getByLabelText("Active"));
    await fireEvent.submit(supplierForm);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.path === "/suppliers/1")?.body).toMatchObject({ active: false }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());

    await fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    const serviceForm = screen.getByRole("button", { name: "Save" }).closest("form")!;
    expect(within(serviceForm).getByLabelText(/References/)).toHaveValue("CPE: PT0002000000000000XX");
    await fireEvent.click(within(serviceForm).getByLabelText("Renews automatically"));
    await fireEvent.submit(serviceForm);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.path === "/services/5")?.body).toMatchObject({ renews_automatically: false, notice_days: 30 }));
  });

  it("shows refusals, an empty list, and cancels forms", async () => {
    const { api } = fakeApi({ "GET /suppliers": [], "GET /services": [], "POST /suppliers": refuse(409, "supplier_exists") });
    renderPage(Services, appFor(api));
    expect(await screen.findByText(/^No suppliers yet\./)).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Add a supplier" }));
    await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "MEO" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("cancels a service form, and says so when it cannot load", async () => {
    const { api } = fakeApi({ "GET /suppliers": [MEO], "GET /services": [POWER] });
    renderPage(Services, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Add a service" }));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();

    const failing = fakeApi({ "GET /suppliers": refuse(500, "boom"), "GET /services": [] });
    renderPage(Services, appFor(failing.api));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("Documents", () => {
  const routes = (extra: Parameters<typeof fakeApi>[0] = {}) => ({ "GET /documents": [CONTRACT], "GET /suppliers": [MEO], "GET /services": [POWER], ...extra });

  const TERMS = {
    service_name: "Electricity",
    supplier_name: "MEO Energia",
    starts_on: "2026-09-13",
    ends_on: "2027-09-13",
    renews_automatically: true,
    lock_in_until: null,
    notice_days: 30,
    billed_every_days: null,
    summary: "No lock-in; 30 days' notice.",
  };
  const withClaude = { ...ADMIN, claude_enabled: true };

  it("offers Claude only when it is set up", async () => {
    const { api } = fakeApi(routes());
    renderPage(Documents, appFor(api));
    await screen.findByRole("link", { name: "MEO Energia contract" });
    expect(screen.queryByRole("button", { name: "Ask Claude" })).not.toBeInTheDocument();
  });

  it("asks Claude about a document and updates its service from the terms", async () => {
    const { api, calls } = fakeApi(
      routes({
        "POST /documents/9/ask": { text: "There is none.", citations: [{ page: 2, quote: "Sem fidelização" }, { page: null, quote: "x" }] },
        "POST /documents/9/terms": TERMS,
        "PUT /services/5": (call) => ({ ...POWER, ...(call.body as object) }),
      }),
    );
    renderPage(Documents, appFor(api, withClaude));
    await fireEvent.click(await screen.findByRole("button", { name: "Ask Claude" }));
    expect(screen.getByRole("heading", { name: "Ask Claude about MEO Energia contract" })).toBeInTheDocument();

    await fireEvent.input(screen.getByLabelText("Question"), { target: { value: "Lock-in?" } });
    await fireEvent.submit(screen.getByLabelText("Question").closest("form")!);
    expect(await screen.findByText("There is none.")).toBeInTheDocument();
    expect(screen.getByText(/p\. 2: “Sem fidelização”/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/documents/9/ask")!.body).toEqual({ question: "Lock-in?" });

    await fireEvent.click(screen.getByRole("button", { name: "Read the terms" }));
    expect(await screen.findByText("No lock-in; 30 days' notice.")).toBeInTheDocument();
    expect(screen.getByText("Notice (days): 30")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Update Electricity at the Quinta with these" }));

    expect(await screen.findByText("Electricity at the Quinta: details updated.")).toBeInTheDocument();
    const body = calls.find((c) => c.method === "PUT")!.body as Record<string, unknown>;
    expect([body.ends_on, body.renews_automatically, body.notice_days, body.lock_in_until]).toEqual(["2027-09-13", true, 30, POWER.lock_in_until]);
    expect(body).not.toHaveProperty("id");

    await fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
  });

  it("describes every term Claude can find", async () => {
    const unlinked = { ...CONTRACT, service_id: null, kind: "terms" as const };
    const { api } = fakeApi(
      routes({
        "GET /documents": [unlinked],
        "POST /documents/9/terms": { ...TERMS, renews_automatically: false, lock_in_until: "2027-07-28", billed_every_days: 30, ends_on: null, notice_days: null },
      }),
    );
    renderPage(Documents, appFor(api, withClaude));
    await fireEvent.click(await screen.findByRole("button", { name: "Ask Claude" }));
    await fireEvent.click(screen.getByRole("button", { name: "Read the terms" }));

    expect(await screen.findByText("Billed every (days): 30")).toBeInTheDocument();
    expect(screen.getByText(/28 Jul 2027/)).toBeInTheDocument();
    expect(screen.getByText("Link this document to a service to update it with these.")).toBeInTheDocument();
  });

  it("says why Claude gave no answer, and offers no terms for other documents", async () => {
    const { api } = fakeApi(
      routes({
        "GET /documents": [{ ...CONTRACT, kind: "info" }],
        "POST /documents/9/ask": () => refuse(502, "claude_declined"),
      }),
    );
    renderPage(Documents, appFor(api, withClaude));
    await fireEvent.click(await screen.findByRole("button", { name: "Ask Claude" }));
    expect(screen.queryByRole("button", { name: "Read the terms" })).not.toBeInTheDocument();
    await fireEvent.input(screen.getByLabelText("Question"), { target: { value: "Why?" } });
    await fireEvent.submit(screen.getByLabelText("Question").closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Claude did not answer this one.");
  });

  it("lists documents with their kind, date, supplier and service", async () => {
    const { api } = fakeApi(routes({ "GET /documents": [CONTRACT, { ...CONTRACT, id: 10, title: "Scan", has_text: false, dated: null, supplier_id: null, service_id: null, kind: "other" }] }));
    renderPage(Documents, appFor(api));

    expect(await screen.findByRole("link", { name: "MEO Energia contract" })).toHaveAttribute("href", "/api/documents/9/file");
    await waitFor(() => expect(screen.getByText(/Contract · 5 Sept? 2026 · MEO Energia · Electricity at the Quinta/)).toBeInTheDocument());
    expect(screen.getByText("No text found in this file to search by.")).toBeInTheDocument();
  });

  it("searches the text and shows where it matched", async () => {
    const { api, calls } = fakeApi(routes({ "GET /documents": (call) => (call.query.get("q") ? [{ ...CONTRACT, excerpt: "…pré-aviso máximo de 1 mês…" }] : []) }));
    renderPage(Documents, appFor(api));
    expect(await screen.findByText(/^No documents yet\./)).toBeInTheDocument();

    await fireEvent.input(screen.getByLabelText("Search"), { target: { value: "pré-aviso" } });
    vi.advanceTimersByTime(300);
    expect(await screen.findByText("…pré-aviso máximo de 1 mês…")).toBeInTheDocument();
    expect(calls.at(-1)!.query.get("q")).toBe("pré-aviso");

    await fireEvent.change(screen.getByLabelText("Type"), { target: { value: "terms" } });
    await waitFor(() => expect(calls.at(-1)!.query.get("kind")).toBe("terms"));
  });

  it("opens filtered to a service, and says when nothing matches", async () => {
    history.replaceState(null, "", "/documents?service=5");
    const { api, calls } = fakeApi(routes({ "GET /documents": [] }));
    renderPage(Documents, appFor(api));
    expect(await screen.findByText("No documents match.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/documents")!.query.get("service_id")).toBe("5");
  });

  it("uploads a file with its details", async () => {
    const { api, calls } = fakeApi(routes({ "POST /documents": CONTRACT }));
    renderPage(Documents, appFor(api));
    await screen.findByRole("link", { name: "MEO Energia contract" });
    const input = screen.getByLabelText("Add a document") as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [] } });
    await fireEvent.change(input, { target: { files: [new File(["%PDF"], "Condições.pdf", { type: "application/pdf" })] } });

    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    expect(within(form).getByLabelText("Title")).toHaveValue("Condições");
    await fireEvent.change(within(form).getByLabelText("Type"), { target: { value: "terms" } });
    await fireEvent.input(within(form).getByLabelText("Date on the document"), { target: { value: "2026-09-05" } });
    await fireEvent.change(within(form).getByLabelText("Supplier"), { target: { value: String(MEO.id) } });
    await fireEvent.submit(form);

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const sent = calls.find((c) => c.method === "POST")!.body as FormData;
    expect([sent.get("title"), sent.get("kind"), sent.get("dated"), sent.get("supplier_id"), sent.get("service_id")]).toEqual([
      "Condições", "terms", "2026-09-05", "1", null,
    ]);
  });

  it("edits and deletes a document", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi(routes({ "PUT /documents/9": CONTRACT, "DELETE /documents/9": () => undefined }));
    renderPage(Documents, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    expect(within(form).getByLabelText("Service")).toBeInTheDocument();
    await fireEvent.input(within(form).getByLabelText("Title"), { target: { value: "Signed contract" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ title: "Signed contract", service_id: POWER.id, supplier_id: MEO.id, dated: "2026-09-05" }));

    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("shows refusals and keeps a document when deleting is not confirmed", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { api, calls } = fakeApi(routes({ "PUT /documents/9": refuse(422, "unknown_service"), "DELETE /documents/9": refuse(500, "boom") }));
    renderPage(Documents, appFor(api));
    await fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    confirm.mockReturnValue(true);
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown_service");
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("says so when it cannot load", async () => {
    const { api } = fakeApi({ "GET /documents": refuse(500, "boom"), "GET /suppliers": refuse(500, "boom"), "GET /services": [] });
    renderPage(Documents, appFor(api));
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("boom");
  });
});

describe("a bill's service", () => {
  it("fills in the supplier and the first line's category, and is saved", async () => {
    const { api, calls } = fakeApi({ "GET /services": [POWER, { ...POWER, id: 6, name: "Ended", active: false }], "GET /suppliers": [MEO], "POST /bills": aBill({ id: 42 }) });
    renderPage(BillForm, appFor(api));
    await screen.findByRole("option", { name: "Electricity at the Quinta" });
    expect(screen.queryByRole("option", { name: "Ended" })).not.toBeInTheDocument();

    await fireEvent.change(screen.getByLabelText(/^Service/), { target: { value: String(POWER.id) } });
    expect(screen.getByLabelText("Supplier")).toHaveValue("MEO Energia");
    expect(screen.getByLabelText("Category")).toHaveValue(String(ELECTRICITY.id));
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "10" } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect((calls.find((c) => c.method === "POST")!.body as { service_id: number }).service_id).toBe(POWER.id));
  });

  it("leaves what is already filled in alone, and keeps a bill's ended service", async () => {
    const { api } = fakeApi({
      "GET /services": [{ ...POWER, active: false }],
      "GET /suppliers": [MEO],
      "GET /bills/7": aBill({ service_id: POWER.id, supplier: "MEO", lines: [{ ...aBill().lines[0], category_id: ROAD.id }] }),
    });
    renderPage(BillForm, appFor(api), { id: 7 });
    await screen.findByDisplayValue("MEO");
    await waitFor(() => expect(screen.getByLabelText(/^Service/)).toHaveValue(String(POWER.id)));
    await fireEvent.change(screen.getByLabelText(/^Service/), { target: { value: String(POWER.id) } });

    expect(screen.getByLabelText("Supplier")).toHaveValue("MEO");
    expect(screen.getByLabelText("Category")).toHaveValue(String(ROAD.id));
  });

  it("is simply left out when the services cannot load", async () => {
    const { api } = fakeApi({ "GET /services": refuse(500, "boom") });
    renderPage(BillForm, appFor(api));
    await fireEvent.change(screen.getByLabelText(/^Service/), { target: { value: "" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
