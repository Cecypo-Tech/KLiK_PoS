import { describe, expect, it, vi } from "vitest";
import { WAREHOUSE_HEADER, withWarehouseHeader } from "./warehouseHeader";

const sent = (base: ReturnType<typeof vi.fn>) => new Headers(base.mock.calls[0][1]?.headers);

describe("withWarehouseHeader", () => {
  it("sends the picked warehouse with an api request", async () => {
    const base = vi.fn().mockResolvedValue(new Response("{}"));
    await withWarehouseHeader(base, () => "Stores B - DC")("/api/method/x", { headers: { A: "1" } });
    expect(decodeURIComponent(sent(base).get(WAREHOUSE_HEADER) ?? "")).toBe("Stores B - DC");
    expect(sent(base).get("A")).toBe("1");
  });

  it("sends nothing when no warehouse is picked", async () => {
    const base = vi.fn().mockResolvedValue(new Response("{}"));
    await withWarehouseHeader(base, () => null)("/api/method/x");
    expect(sent(base).has(WAREHOUSE_HEADER)).toBe(false);
  });

  it("never sends it anywhere but this site's api", async () => {
    const base = vi.fn().mockResolvedValue(new Response("{}"));
    await withWarehouseHeader(base, () => "Stores B - DC")("https://cdn.example.com/x.js");
    expect(sent(base).has(WAREHOUSE_HEADER)).toBe(false);
  });

  it("sends a warehouse named in any script", async () => {
    // A header value must be Latin-1; an Arabic name would fail every request before it left.
    const base = vi.fn().mockResolvedValue(new Response("{}"));
    await withWarehouseHeader(base, () => "مستودع - ش")("/api/method/x");
    expect(decodeURIComponent(sent(base).get(WAREHOUSE_HEADER) ?? "")).toBe("مستودع - ش");
  });
});
