/** Choices for return value that cannot go back as cash (the credit router).

Named customers keep the credit (default) or exchange now. Walk In may only
exchange - nobody can prove the credit is theirs later - unless a manager
override restores keep. The server enforces the same rule; this only decides
what the dialog offers.
*/

export type CreditAction = "keep" | "exchange";

export function creditChoices(isWalkin: boolean, hasManagerOverride: boolean): CreditAction[] {
  if (isWalkin && !hasManagerOverride) return ["exchange"];
  return ["keep", "exchange"];
}
