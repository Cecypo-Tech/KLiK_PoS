import { extractErrorMessage } from "../utils/errorExtraction";

export interface Supervisor {
  name: string;
  full_name: string;
}

export interface AuthoriseResult {
  ok: boolean;
  token: string | null;
  message: string;
}

const csrf = () => (window as { csrf_token?: string }).csrf_token as string;

async function call(method: string, body?: object) {
  const response = await fetch(`/api/method/klik_pos.api.price_floor.${method}`, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf() },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(extractErrorMessage(result, "Request failed"));
  return result.message;
}

/** Users who may authorise a price below the minimum at this till. */
export async function getSupervisors(): Promise<Supervisor[]> {
  return (await call("get_supervisors")) || [];
}

/** A supervisor's PIN for the cart as previewed; the token goes with the checkout. */
export async function authorisePriceFloor(data: object, supervisor: string, pin: string): Promise<AuthoriseResult> {
  return call("authorise", { data, supervisor, pin });
}
