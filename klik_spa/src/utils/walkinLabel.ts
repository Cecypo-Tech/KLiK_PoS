/** The walk-in buyer's name to show under the customer in Invoice History, or null when
 * there is none or it would only repeat the customer. Walk-in sales and held orders all sit
 * under one customer; without this they cannot be told apart. */
export function walkinSubline(customer: string, walkinName?: string | null): string | null {
  const name = (walkinName ?? "").trim();
  if (!name || name.toLowerCase() === (customer ?? "").trim().toLowerCase()) return null;
  return name;
}
