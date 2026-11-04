/**
 * The dashboard's till filter. A selection of [] means every till, so these rules never hand
 * back an empty list for "nothing": unticking the last till is refused instead of silently
 * becoming "all tills".
 */

// Every till picked says the same as no filter, and the label then reads "All tills".
const normalize = (selected: string[], all: string[]) => (selected.length === all.length ? [] : selected);

export function toggleTill(selected: string[], all: string[], till: string): string[] {
  const current = selected.length === 0 ? all : selected;
  if (current.includes(till)) {
    if (current.length === 1) return selected;
    return normalize(current.filter((name) => name !== till), all);
  }
  // Keep the list's order, so the label and the menu agree.
  return normalize(all.filter((name) => name === till || current.includes(name)), all);
}

export const onlyTill = (all: string[], till: string) => normalize([till], all);

/** The search results as the selection; no results changes nothing (returns all). */
export const onlyTills = (all: string[], matches: string[]) =>
  matches.length === 0 ? [] : normalize(all.filter((name) => matches.includes(name)), all);

export function filterTills(all: string[], query: string): string[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return all.filter((name) => words.every((word) => name.toLowerCase().includes(word)));
}
