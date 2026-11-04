/** Quote mode is on unless the till's "Allow Quotes" box is unticked (missing = on). */
export const quotesAllowed = (posDetails?: { custom_allow_quotes?: boolean | number | string } | null) =>
  ![0, "0", false].includes(posDetails?.custom_allow_quotes as never);
