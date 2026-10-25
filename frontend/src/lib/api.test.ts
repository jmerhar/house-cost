import { describe, expect, it, vi } from "vitest";
import { Api, ApiError } from "./api";

function answering(status: number, body: unknown, statusText = ""): typeof fetch {
  return vi.fn(async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status, statusText }),
  ) as unknown as typeof fetch;
}

describe("Api", () => {
  it("asks /api/health for JSON, sending the session cookie", async () => {
    const fetcher = answering(200, { status: "ok", database: "connected", version: "1.2.3" });
    const health = await new Api("/api", fetcher).health();

    expect(health.version).toBe("1.2.3");
    expect(fetcher).toHaveBeenCalledWith("/api/health", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
  });

  it("reports the server's own explanation of a failure", async () => {
    const api = new Api("/api", answering(503, { detail: "database locked" }));

    await expect(api.health()).rejects.toEqual(new ApiError(503, "database locked"));
  });

  it("falls back to the status text when the failure has no explanation", async () => {
    const api = new Api("/api", answering(502, "<html>bad gateway</html>", "Bad Gateway"));

    await expect(api.health()).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("names the status when there is no status text either", async () => {
    const api = new Api("/api", answering(500, { detail: { nested: true } }));

    await expect(api.health()).rejects.toMatchObject({ status: 500, message: "HTTP 500" });
  });

  it("reports an unreachable server as status 0", async () => {
    const fetcher = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    await expect(new Api("/api", fetcher).health()).rejects.toMatchObject({
      status: 0,
      message: "Failed to fetch",
      name: "ApiError",
    });
  });

  it("reports a non-Error rejection as status 0 too", async () => {
    const fetcher = vi.fn(async () => {
      throw "offline";
    }) as unknown as typeof fetch;

    await expect(new Api("/api", fetcher).health()).rejects.toMatchObject({ status: 0, message: "offline" });
  });

  it("uses the global fetch by default", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", database: "connected", version: "9.9.9" })),
    );
    expect((await new Api().health()).version).toBe("9.9.9");
    expect(spy).toHaveBeenCalledWith("/api/health", expect.anything());
    spy.mockRestore();
  });
});
