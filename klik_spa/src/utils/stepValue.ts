/** The value one step up (direction 1) or down (-1) from `current`, kept within [min, max]. */
export function stepValue(
  current: number | string,
  direction: 1 | -1,
  step = 1,
  min = 0,
  max = Number.POSITIVE_INFINITY,
): number {
  const value = Number(current) || 0;
  const next = Math.round((value + direction * step) * 100) / 100;
  return Math.min(max, Math.max(min, next));
}
