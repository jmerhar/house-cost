import { describe, expect, it, vi } from "vitest";
import { Api, ApiError, WRITE_HEADER } from "./api";
import { fakeApi, refuse } from "../testing";

function answering(status: number, body: unknown, statusText = ""): typeof fetch {
  return vi.fn(async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status, statusText }),
  ) as unknown as typeof fetch;
}

describe("Api", () => {
  it("reads with JSON and the session cookie, and no write header", async () => {
    const fetcher = answering(200, { status: "ok", database: "connected", version: "1.2.3" });
    expect((await new Api("/api", fetcher).health()).version).toBe("1.2.3");
    expect(fetcher).toHaveBeenCalledWith("/api/health", {
      method: "GET",
      headers: { Accept: "application/json" },
      body: undefined,
      credentials: "same-origin",
    });
  });

  it("writes JSON with the write header", async () => {
    const fetcher = answering(201, { id: 3, name: "Third", position: 2, active: true });
    await new Api("/api", fetcher).createHousehold({ name: "Third", position: 2, active: true });
    expect(fetcher).toHaveBeenCalledWith("/api/households", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json", ...WRITE_HEADER },
      body: JSON.stringify({ name: "Third", position: 2, active: true }),
      credentials: "same-origin",
    });
  });

  it("sends a file as a form, letting the browser set its type", async () => {
    const { api, calls } = fakeApi({ "POST /attachments": { id: 1, filename: "bill.pdf", content_type: "application/pdf", size: 3 } });
    const file = new File(["%PDF"], "bill.pdf", { type: "application/pdf" });
    await api.attach(file, { bill_id: 7 });

    const form = calls[0].body as FormData;
    expect(form.get("bill_id")).toBe("7");
    expect((form.get("file") as File).name).toBe("bill.pdf");
  });

  it("builds queries without the empty parts", async () => {
    const { api, calls } = fakeApi({ "GET /bills": { items: [], total: 0 } });
    await api.bills({ q: "meo", year: "", category_id: undefined, paid_by_id: null, limit: 50 });
    expect(calls[0].query.toString()).toBe("q=meo&limit=50");
  });

  it("answers nothing for a 204", async () => {
    const { api } = fakeApi({ "DELETE /bills/7": () => undefined });
    expect(await api.deleteBill(7)).toBeUndefined();
  });

  it("knows where files and the CSV export are", () => {
    const api = new Api();
    expect(api.attachmentUrl(3)).toBe("/api/attachments/3");
    expect(api.csvUrl(2026)).toBe("/api/reports/bills.csv?year=2026");
    expect(api.csvUrl()).toBe("/api/reports/bills.csv");
  });

  it("reports the server's refusal code", async () => {
    const { api } = fakeApi({ "POST /bills": refuse(422, "no_rule") });
    await expect(api.createBill({} as never)).rejects.toEqual(new ApiError(422, "no_rule"));
  });

  it("reports a validation failure as invalid", async () => {
    const api = new Api("/api", answering(422, { detail: [{ loc: ["body"], msg: "x" }] }));
    await expect(api.me()).rejects.toMatchObject({ status: 422, message: "invalid" });
  });

  it("falls back to the status text, then the status", async () => {
    await expect(new Api("/api", answering(502, "<html>", "Bad Gateway")).me()).rejects.toMatchObject({
      message: "Bad Gateway",
    });
    await expect(new Api("/api", answering(500, { detail: 5 })).me()).rejects.toMatchObject({ message: "HTTP 500" });
  });

  it("reports an unreachable server as status 0", async () => {
    const offline = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const odd = vi.fn(async () => {
      throw "offline";
    }) as unknown as typeof fetch;

    await expect(new Api("/api", offline).me()).rejects.toMatchObject({ status: 0, message: "Failed to fetch", name: "ApiError" });
    await expect(new Api("/api", odd).me()).rejects.toMatchObject({ status: 0, message: "offline" });
  });

  it("uses the global fetch by default", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ required: true })));
    expect(await new Api().setupState()).toEqual({ required: true });
    spy.mockRestore();
  });

  it("names every endpoint the interface uses", async () => {
    const { api, calls } = fakeApi({});
    const attempts: (() => Promise<unknown>)[] = [
      () => api.setUp({ household_name: "H", name: "N", login: "n", password: "x".repeat(10) }),
      () => api.logIn("n", "p"),
      () => api.logOut(),
      () => api.updateMe({ name: "N" }),
      () => api.sessions(),
      () => api.endSession(1),
      () => api.households(),
      () => api.updateHousehold(1, { name: "H" }),
      () => api.people(),
      () => api.createPerson({ name: "N", login: "n", household_id: 1, password: "x".repeat(10) }),
      () => api.updatePerson(1, { name: "N", login: "n", role: "member", household_id: 1, active: true }),
      () => api.categories(),
      () => api.createCategory({ name: "C" }),
      () => api.updateCategory(1, { name: "C" }),
      () => api.rules(1),
      () => api.createRule({ category_id: 1, effective_from: "2026-01-01", shares: [] }),
      () => api.deleteRule(1),
      () => api.splitPreview(1, "2026-01-01", 100),
      () => api.bill(1),
      () => api.updateBill(1, {} as never),
      () => api.settlements({ year: 2026 }),
      () => api.createSettlement({ date: "2026-01-01", from_id: 1, to_id: 2, amount_cents: 1 }),
      () => api.updateSettlement(1, { date: "2026-01-01", from_id: 1, to_id: 2, amount_cents: 1 }),
      () => api.deleteSettlement(1),
      () => api.deleteAttachment(1),
      () => api.balances(),
      () => api.summary(2026),
      () => api.audit({ limit: 5 }),
      () => api.settings(),
      () => api.updateSettings({ reconciliation_enabled: true }),
      () => api.reconciliations(),
      () => api.reconciliation(1),
      () => api.createReconciliation({ period_start: "2026-01-01", period_end: "2026-12-31" }),
      () => api.updateReconciliation(1, { period_start: "2026-01-01", period_end: "2026-12-31" }),
      () => api.closeReconciliation(1),
      () => api.deleteReconciliation(1),
    ];
    for (const attempt of attempts) await attempt().catch(() => undefined);

    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /setup",
      "POST /auth/login",
      "POST /auth/logout",
      "PATCH /auth/me",
      "GET /auth/sessions",
      "DELETE /auth/sessions/1",
      "GET /households",
      "PUT /households/1",
      "GET /people",
      "POST /people",
      "PUT /people/1",
      "GET /categories",
      "POST /categories",
      "PUT /categories/1",
      "GET /rules",
      "POST /rules",
      "DELETE /rules/1",
      "GET /split-preview",
      "GET /bills/1",
      "PUT /bills/1",
      "GET /settlements",
      "POST /settlements",
      "PUT /settlements/1",
      "DELETE /settlements/1",
      "DELETE /attachments/1",
      "GET /balances",
      "GET /reports/summary",
      "GET /audit",
      "GET /settings",
      "PUT /settings",
      "GET /reconciliations",
      "GET /reconciliations/1",
      "POST /reconciliations",
      "PUT /reconciliations/1",
      "POST /reconciliations/1/close",
      "DELETE /reconciliations/1",
    ]);
    expect(calls[14].query.get("category_id")).toBe("1");
    expect(calls[17].query.toString()).toBe("category_id=1&on=2026-01-01&amount_cents=100");
  });
});
