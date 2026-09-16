/**
 * The cashier's own open shift that stops them opening a till, as returned by
 * klik_pos.api.pos_entry.opening_conflict. Other cashiers' shifts are never in the way.
 */
export interface OpeningConflict {
  kind: "own_open" | "own_stale" | "own_other_profile" | "till_open" | "till_stale";
  entry: string;
  pos_profile: string;
  period_start_date: string;
  user: string;
  user_name: string;
}

export interface ConflictNotice {
  message: string;
  /** continue: carry on in the open shift. close: go to Closing Shift first.
   *  join: join another cashier's open shift. join_close: join it, then close it. */
  action: "continue" | "close" | "join" | "join_close";
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
    default:
      return {
        message: `Your shift ${entry} on ${pos_profile} is still open. Close it before opening another till.`,
        action: "close",
      };
  }
}
