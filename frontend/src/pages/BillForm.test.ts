import { fireEvent, screen, waitFor, within } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigate, route } from "../lib/router.svelte";
import { ELECTRICITY, LUCIA, OWNERS, ROAD, aBill, appFor, fakeApi, refuse, renderPage, type Call } from "../testing";
import BillForm from "./BillForm.svelte";

const preview = (call: Call) => {
  const cents = Number(call.query.get("amount_cents"));
  const lucia = call.query.get("category_id") === String(ROAD.id) ? Math.round(cents / 4) : Math.ceil(cents / 2);
  return {
    rule_id: 1,
    shares: [
      { household_id: LUCIA.id, amount_cents: lucia },
      { household_id: OWNERS.id, amount_cents: cents - lucia },
    ],
  };
};

beforeEach(() => {
  history.replaceState(null, "", "/elsewhere");
  navigate("/bills/new", { replace: true });
});
afterEach(() => vi.restoreAllMocks());

describe("a new bill", () => {
  it("is paid by the person's household and dated today, and shows each line's split", async () => {
    const { api } = fakeApi({ "GET /split-preview": preview });
    renderPage(BillForm, appFor(api));

    expect(screen.getByLabelText("Paid by")).toHaveValue(String(LUCIA.id));
    expect((screen.getByLabelText("Date on the bill") as HTMLInputElement).value).toMatch(/^\d{4}-\d\d-\d\d$/);
    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ELECTRICITY.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "287,59" } });

    expect(await screen.findByText("Split: Lúcia €143.80 · Tiago + Marta €143.79", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.getByText("€287.59")).toBeInTheDocument();
  });

  it("explains a line no rule can split", async () => {
    const { api } = fakeApi({ "GET /split-preview": refuse(422, "no_rule") });
    renderPage(BillForm, appFor(api));
    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ROAD.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "10" } });

    expect(await screen.findByText(/no split rule in force/, {}, { timeout: 2000 })).toHaveClass("problem");
  });

  it("is saved with all its lines and opens as itself, where files can be attached", async () => {
    const { api, calls } = fakeApi({ "GET /split-preview": preview, "POST /bills": aBill({ id: 42 }) });
    renderPage(BillForm, appFor(api));
    await fireEvent.input(screen.getByLabelText("Supplier"), { target: { value: "MEO" } });
    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ELECTRICITY.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "18,37" } });
    await fireEvent.click(screen.getByRole("button", { name: "Add a line" }));
    const [, second] = screen.getAllByRole("listitem");
    await fireEvent.change(within(second).getByLabelText("Category"), { target: { value: String(ROAD.id) } });
    await fireEvent.input(within(second).getByLabelText("Amount (€)"), { target: { value: "1,61" } });
    await fireEvent.input(within(second).getByLabelText(/What it is for/), { target: { value: "Gravel" } });

    expect(screen.getByText("Files can be attached once the bill is saved.")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills/42"));
    const sent = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(sent).toMatchObject({
      supplier: "MEO",
      paid_by_id: LUCIA.id,
      invoice_number: null,
      period_start: null,
      lines: [
        { id: null, category_id: ELECTRICITY.id, amount_cents: 1837, description: "" },
        { id: null, category_id: ROAD.id, amount_cents: 161, description: "Gravel" },
      ],
    });
  });

  it("can lose a line again", async () => {
    const { api } = fakeApi({});
    renderPage(BillForm, appFor(api));
    expect(screen.queryByRole("button", { name: "Remove this line" })).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Add a line" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    await fireEvent.click(screen.getAllByRole("button", { name: "Remove this line" })[0]);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("refuses an amount it cannot read", async () => {
    const { api, calls } = fakeApi({});
    renderPage(BillForm, appFor(api));
    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ROAD.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "twelve" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    expect(screen.getByRole("alert")).toHaveTextContent("Enter an amount in euros");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("shows the API's refusal", async () => {
    const { api } = fakeApi({ "POST /bills": refuse(422, "no_rule") });
    renderPage(BillForm, appFor(api));
    await fireEvent.change(screen.getByLabelText("Category"), { target: { value: String(ROAD.id) } });
    await fireEvent.input(screen.getByLabelText("Amount (€)"), { target: { value: "5" } });
    await fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("no split rule in force");
  });
});

describe("an existing bill", () => {
  it("is filled in, corrected keeping its lines' ids, and goes back to the list", async () => {
    const { api, calls } = fakeApi({ "GET /bills/7": aBill(), "PUT /bills/7": aBill(), "GET /split-preview": preview });
    renderPage(BillForm, appFor(api), { id: 7 });

    expect(await screen.findByDisplayValue("MEO Energia")).toBeInTheDocument();
    expect(screen.getByLabelText("Amount (€)")).toHaveValue("287.59");
    expect(screen.getByLabelText("Paid by")).toHaveValue(String(OWNERS.id));
    await fireEvent.input(screen.getByLabelText("Description"), { target: { value: "October" } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(route.path).toBe("/bills"));
    const sent = calls.find((c) => c.method === "PUT")!.body as Record<string, unknown>;
    expect(sent).toMatchObject({
      description: "October",
      invoice_number: "FA MEA26/100001",
      period_end: "2026-10-16",
      due_date: "2026-11-03",
      lines: [{ id: 70, amount_cents: 28759 }],
    });
  });

  it("can be deleted after confirming", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api, calls } = fakeApi({ "GET /bills/7": aBill(), "DELETE /bills/7": () => undefined });
    renderPage(BillForm, appFor(api), { id: 7 });
    await fireEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => expect(route.path).toBe("/bills"));
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("stays when the deletion is not confirmed or is refused", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { api, calls } = fakeApi({ "GET /bills/7": aBill(), "DELETE /bills/7": refuse(409, "period_closed") });
    renderPage(BillForm, appFor(api), { id: 7 });
    await fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    confirm.mockReturnValue(true);
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reconciled and closed");
  });

  it("takes files, lists them and lets them go", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const attachment = { id: 5, filename: "bill.pdf", content_type: "application/pdf", size: 312_000 };
    const { api, calls } = fakeApi({
      "GET /bills/7": aBill(),
      "POST /attachments": attachment,
      "DELETE /attachments/5": () => undefined,
    });
    renderPage(BillForm, appFor(api), { id: 7 });
    const input = (await screen.findByLabelText("Attach a PDF or a photo")) as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [new File(["%PDF"], "bill.pdf", { type: "application/pdf" })] } });

    const link = await screen.findByRole("link", { name: "bill.pdf" });
    expect(link).toHaveAttribute("href", "/api/attachments/5");
    expect(screen.getByText("312 kB")).toBeInTheDocument();
    expect((calls.find((c) => c.method === "POST")!.body as FormData).get("bill_id")).toBe("7");

    await fireEvent.click(screen.getByRole("button", { name: "Remove file" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "bill.pdf" })).not.toBeInTheDocument());
  });

  it("reports a file that cannot be attached or removed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { api } = fakeApi({
      "GET /bills/7": aBill({ attachments: [{ id: 5, filename: "a.pdf", content_type: "application/pdf", size: 10 }] }),
      "POST /attachments": refuse(415, "unsupported_file"),
      "DELETE /attachments/5": refuse(409, "period_closed"),
    });
    renderPage(BillForm, appFor(api), { id: 7 });
    const input = (await screen.findByLabelText("Attach a PDF or a photo")) as HTMLInputElement;
    await fireEvent.change(input, { target: { files: [new File(["x"], "note.txt")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files and photos");

    await fireEvent.click(screen.getByRole("button", { name: "Remove file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reconciled and closed");
  });

  it("is read-only once its period is reconciled", async () => {
    const { api } = fakeApi({
      "GET /bills/7": aBill({ locked: true, attachments: [{ id: 5, filename: "a.pdf", content_type: "application/pdf", size: 10 }] }),
    });
    renderPage(BillForm, appFor(api), { id: 7 });

    expect(await screen.findByText(/reconciled and closed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Supplier")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove file" })).not.toBeInTheDocument();
  });

  it("keeps an inactive category it was filed under", async () => {
    const { api } = fakeApi({ "GET /bills/7": aBill() });
    const app = appFor(api);
    app.categories = [{ ...ELECTRICITY, active: false }, ROAD];
    renderPage(BillForm, app, { id: 7 });

    await screen.findByDisplayValue("MEO Energia");
    expect(screen.getByLabelText("Category")).toHaveValue(String(ELECTRICITY.id));
  });

  it("says so when it cannot be loaded", async () => {
    const { api } = fakeApi({ "GET /bills/7": refuse(404, "not_found") });
    renderPage(BillForm, appFor(api), { id: 7 });
    expect(await screen.findByRole("alert")).toHaveTextContent("not_found");
  });
});
