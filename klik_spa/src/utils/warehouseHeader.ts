export const WAREHOUSE_HEADER = "X-Klik-Warehouse";

type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

/**
 * The till's picked warehouse rides on every request to this site's api, so the server builds
 * sales, holds, scans and stock lookups from it (klik_pos.klik_pos.utils.requested_warehouse).
 * Nothing stores it server-side.
 */
export function withWarehouseHeader(base: Fetch, picked: () => string | null | undefined): Fetch {
  return (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const warehouse = picked();
    if (!warehouse || !url.startsWith("/api/")) return base(input, init);
    const headers = new Headers(init?.headers);
    // Header values are Latin-1 only; the server unquotes it.
    headers.set(WAREHOUSE_HEADER, encodeURIComponent(warehouse));
    return base(input, { ...init, headers });
  };
}

/** The warehouse to send: a pick away from the till's own, else none (the server uses the till's). */
export function pickToSend(picked: string | null | undefined, till: { warehouse?: string } | null | undefined) {
  return picked && picked !== till?.warehouse ? picked : null;
}
