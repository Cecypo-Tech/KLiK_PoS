/** One of several shifts open on a till, offered to a manager to close individually. */
export interface OpenShiftRow {
  entry: string;
  user: string;
  user_name: string;
  period_start_date: string;
  stale: boolean;
}

/**
 * The shift that stands in the way of opening a till, as returned by
 * klik_pos.api.pos_entry.opening_conflict. A stale shift belonging to another cashier, or a
 * till with more than one open shift, is now something only a manager can resolve.
 */
export interface OpeningConflict {
  kind:
    | "own_open"
    | "own_stale"
    | "own_other_profile"
    | "till_open"
    | "till_stale"
    | "till_needs_manager"
    | "till_multiple";
  entry: string;
  pos_profile: string;
  period_start_date: string;
  user: string;
  user_name: string;
  manager?: boolean;
  open_shifts?: OpenShiftRow[];
}

export interface ConflictNotice {
  message: string;
  /** continue: carry on in the open shift. close: go to Closing Shift first.
   *  join: join another cashier's open shift. join_close: join it, then close it (a
   *  manager only, now that a stale shift can no longer be joined by anyone else).
   *  none: message only, nothing the caller can do here. close_each: a manager is offered
   *  each open shift on the till, to close one at a time. */
  action: "continue" | "close" | "join" | "join_close" | "none" | "close_each";
}

export function conflictNotice(conflict: OpeningConflict): ConflictNotice {
  const { entry, pos_profile } = conflict;
  switch (conflict.kind) {
    case "own_open":
      return {
        message: `Your shift ${entry} on ${pos_profile} is already open.`,
        action: "continue",
      };
    case "own_stale":
      return {
        message: `Your shift ${entry} on ${pos_profile} was opened on an earlier day. Close it before opening a new one.`,
        action: "close",
      };
    case "till_open":
      return {
        message: `${conflict.user_name} already has shift ${entry} open on ${pos_profile}. Join it to sell on this till.`,
        action: "join",
      };
    case "till_stale":
      return {
        message: `Shift ${entry} on ${pos_profile} was opened on an earlier day. Join it and close it before selling.`,
        action: "join_close",
      };
    case "till_needs_manager": {
      const shifts = conflict.open_shifts ?? [];
      if (shifts.length > 1) {
        return {
          message: `Till ${pos_profile} has ${shifts.length} open shifts. A manager must close the extra shifts first.`,
          action: "none",
        };
      }
      return {
        message: `Shift ${entry} on ${pos_profile} was opened on ${String(conflict.period_start_date).slice(0, 10)} by ${conflict.user_name}. A manager must close it before this till can sell.`,
        action: "none",
      };
    }
    case "till_multiple":
      return {
        message: `Till ${pos_profile} has ${(conflict.open_shifts ?? []).length} open shifts. Close each one before opening a new shift.`,
        action: "close_each",
      };
    default:
      return {
        message: `Your shift ${entry} on ${pos_profile} is still open. Close it before opening another till.`,
        action: "close",
      };
  }
}
