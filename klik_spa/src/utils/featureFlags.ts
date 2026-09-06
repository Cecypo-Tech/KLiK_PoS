/**
 * Build-time feature switches.
 *
 * These are deliberately plain constants rather than settings: they turn off features that are
 * not merely unconfigured but cannot legally or operationally be used, so an operator should
 * not be able to switch them back on from the UI by mistake.
 */

/**
 * Multi-Invoice Return — returning items across several invoices in one credit note.
 *
 * OFF because Kenya's TIMS/eTIMS rules require a credit note to reference the single original
 * invoice it reverses, so one note spanning several invoices cannot be transmitted correctly.
 * Single-invoice returns are unaffected and remain available.
 *
 * The feature's code is intentionally left in place rather than deleted — flip this to true to
 * restore it for a deployment where the requirement does not apply.
 */
export const MULTI_INVOICE_RETURN_ENABLED = false;

/**
 * Sales Dashboard v2 — the server-aggregated page that balances billed against collected
 * and deni, replacing the client-side sums of the original.
 *
 * OFF until the validation script has been run against a real closed shift on the site
 * being deployed to: the point of v2 is that its numbers can be checked, so it should not
 * be turned on anywhere they have not been. The old page keeps serving meanwhile, and is
 * deleted a week after the deploy that flips this.
 */
export const DASHBOARD_V2_ENABLED = false;
