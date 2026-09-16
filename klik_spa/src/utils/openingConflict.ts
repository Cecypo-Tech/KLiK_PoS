/**
 * The cashier's own open shift that stops them opening a till, as returned by
 * klik_pos.api.pos_entry.opening_conflict. Other cashiers' shifts are never in the way.
 */
export interface OpeningConflict {
  kind: "own_open" | "own_stale" | "own_other_profile";
  entry: string;
  pos_profile: string;
  period_start_date: string;
}

export interface ConflictNotice {
  message: string;
  /** continue: carry on in the open shift. close: go to Closing Shift first. */
  action: "continue" | "close";
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
    default:
      return {
        message: `Your shift ${entry} on ${pos_profile} is still open. Close it before opening another till.`,
        action: "close",
      };
  }
}
