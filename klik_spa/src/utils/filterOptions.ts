/** Options whose label (or id) contains the query, ignoring case; all of them for a blank query. */
export function filterOptions<T>(
  options: T[],
  query: string,
  label: (option: T) => string,
  id?: (option: T) => string,
): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return options;
  return options.filter(
    (option) =>
      (label(option) || "").toLowerCase().includes(needle) ||
      (id ? (id(option) || "").toLowerCase().includes(needle) : false),
  );
}

/** The next highlighted index after an arrow key, wrapping at both ends; -1 for an empty list. */
export function moveHighlight(current: number, count: number, step: 1 | -1): number {
  if (count <= 0) return -1;
  if (current < 0) return step === 1 ? 0 : count - 1;
  return (current + step + count) % count;
}
