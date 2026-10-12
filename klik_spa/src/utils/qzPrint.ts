import { toast } from "react-toastify";

// Frappe puts throw() messages in _server_messages; surface a concise one.
function failWith(result: { _server_messages?: string; exception?: string }, fallback: string): never {
  const serverMsg = (() => {
    try {
      return JSON.parse(result._server_messages || "[]")
        .map((m: string) => JSON.parse(m).message)
        .join(" ");
    } catch {
      return "";
    }
  })();
  const msg = serverMsg || result.exception || fallback;
  toast.error(msg);
  throw new Error(msg);
}

/**
 * Enqueue a QZ (thermal) reprint of a document through cecypo_qz_extension's
 * print queue. Mirrors services/salesInvoice.ts's fetch+CSRF pattern.
 *
 * The endpoint lives in a separate app (cecypo_qz_extension). If that app is
 * not installed the call 404s — callers only render the button when the
 * POS-Profile-driven `custom_enable_qz_print` flag is on, which is itself
 * only present when that app is installed, so a 404 here is an unexpected
 * misconfiguration worth surfacing.
 */
export async function qzReprint(
  referenceName: string,
  referenceDoctype: string = "Sales Invoice",
  rules?: string[],
): Promise<{ jobCount: number }> {
  const csrfToken = window.csrf_token;

  const response = await fetch(
    "/api/method/cecypo_qz_extension.api.queue.reprint",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
        // Absent = every matching rule; the picker narrows it to the ticked ones.
        ...(rules ? { rules: JSON.stringify(rules) } : {}),
      }),
      credentials: "include",
    },
  );

  const result = await response.json();

  if (!response.ok) failWith(result, "QZ print failed");

  const jobs = Array.isArray(result.message) ? result.message : [];
  if (jobs.length === 0) {
    toast.warn("No print route matched — nothing was sent to a printer.");
  } else {
    toast.success("Sent to printer");
  }
  return { jobCount: jobs.length };
}

/**
 * How many times QZ has printed this document (Printed jobs, not copies) —
 * the "-3" beside the QZ icon, same as the desk sidebar. 0 on any failure:
 * a count is decoration and must never raise a toast.
 */
export async function qzPrintCount(
  referenceName: string,
  referenceDoctype: string = "Sales Invoice",
): Promise<number> {
  const query = new URLSearchParams({
    reference_doctype: referenceDoctype,
    reference_name: referenceName,
  });
  try {
    const response = await fetch(
      `/api/method/cecypo_qz_extension.api.queue.print_count?${query}`,
      { credentials: "include" },
    );
    if (!response.ok) return 0;
    const result = await response.json();
    return Number(result.message) || 0;
  } catch {
    return 0;
  }
}

/** A routing rule the QZ button can print, as cecypo_qz_extension's reprint_options lists it. */
export type QzRuleOption = { rule: string; limit_reached: boolean };

/** The rules the QZ button may print for this document, in priority order. */
export async function qzPrintOptions(
  referenceName: string,
  referenceDoctype: string = "Sales Invoice",
): Promise<QzRuleOption[]> {
  const response = await fetch(
    "/api/method/cecypo_qz_extension.api.queue.reprint_options",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": window.csrf_token,
      },
      body: JSON.stringify({
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
      }),
      credentials: "include",
    },
  );
  const result = await response.json();
  if (!response.ok) failWith(result, "Could not read the QZ print rules");
  return Array.isArray(result.message) ? result.message : [];
}

export type QzNextStep =
  | { kind: "none" }
  | { kind: "limit" }
  | { kind: "print"; rules: string[] }
  | { kind: "choose"; options: QzRuleOption[] };

/** What a QZ button click does with the rules on offer — the desk sidebar's logic. */
export function qzNextStep(options: QzRuleOption[]): QzNextStep {
  if (!options.length) return { kind: "none" };
  if (options.every((o) => o.limit_reached)) return { kind: "limit" };
  const [only] = options;
  if (options.length === 1 && only) return { kind: "print", rules: [only.rule] };
  return { kind: "choose", options };
}
