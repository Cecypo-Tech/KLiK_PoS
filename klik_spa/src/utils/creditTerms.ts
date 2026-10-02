/**
 * A credit sale's due date from Payment Terms (klik_pos.api.payment_terms.credit_terms): the
 * cashier picks terms, the server works out the date. No templates on the site: the till keeps
 * its date field.
 */

export interface CreditTerm {
  name: string;
  /** YYYY-MM-DD, the date these terms give a sale posted today. */
  due_date: string;
}

export interface CreditTerms {
  /** Earliest due date first. */
  templates: CreditTerm[];
  /** The customer's own terms, else the earliest. */
  default: string | null;
}

/** The terms to show selected: the cashier's pick while still offered, else the default. */
export function chooseTerm(terms: CreditTerms | null | undefined, current: string): CreditTerm | null {
  const templates = terms?.templates ?? [];
  if (!templates.length) return null;
  return (
    templates.find((t) => t.name === current)
    ?? templates.find((t) => t.name === terms?.default)
    ?? templates[0]
    ?? null
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function termLabel(term: CreditTerm): string {
  const [year, month, day] = term.due_date.split("-");
  return `${term.name} - due ${day} ${MONTHS[Number(month) - 1] ?? month} ${year}`;
}
