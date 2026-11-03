export const PENDING = "Price Approval Pending";
export const APPROVED = "Price Approved";
/** Window event the till fires after asking a manager, so the watch starts at once. */
export const APPROVAL_REQUESTED_EVENT = "klik:price-approval-requested";

export interface HeldRow {
  name: string;
  approval_state?: string | null;
  owner?: string;
  customer_name?: string;
}

/** My orders that were pending last look: which a manager answered, which still wait.
 * An order gone from the list was checked out or deleted: nothing to say about it. */
export function approvalAnswers<T extends HeldRow>(wasPending: Set<string>, rows: T[], me: string) {
  const mine = rows.filter((r) => r.owner === me);
  const answered = mine.filter((r) => wasPending.has(r.name) && r.approval_state !== PENDING);
  return {
    approved: answered.filter((r) => r.approval_state === APPROVED),
    declined: answered.filter((r) => r.approval_state !== APPROVED),
    pending: new Set(mine.filter((r) => r.approval_state === PENDING).map((r) => r.name)),
  };
}
