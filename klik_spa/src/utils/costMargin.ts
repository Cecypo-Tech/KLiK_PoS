interface TaxInfoLike {
  is_inclusive?: boolean;
  total_tax_rate?: number;
  inclusive_tax_rate?: number;
}

/**
 * The tax rate that is baked into an item's sell price. For mixed tax lines only the
 * inclusive portion counts: an exclusive levy is added on top at the till, not in the rate.
 */
export function getInclusiveTaxRate(taxInfo: TaxInfoLike | null | undefined): number {
  if (!taxInfo) return 0;
  if (taxInfo.inclusive_tax_rate !== undefined && taxInfo.inclusive_tax_rate !== null) {
    return Math.max(0, Number(taxInfo.inclusive_tax_rate) || 0);
  }
  return taxInfo.is_inclusive ? Math.max(0, Number(taxInfo.total_tax_rate) || 0) : 0;
}

interface CostMarginInput {
  sellPrice: number;
  /** Valuation: excludes tax and is per STOCK UOM. */
  costPerStockUom: number;
  inclusiveTaxRate: number;
  /** Stock UOMs per selling UOM. */
  conversionFactor?: number;
}

/**
 * Margin on the basis the till actually collects: the valuation is converted to the selling
 * UOM and grossed up by the tax baked into the sell price, then compared with that price.
 */
export function getCostMargin({ sellPrice, costPerStockUom, inclusiveTaxRate, conversionFactor }: CostMarginInput) {
  const factor = Number(conversionFactor) > 0 ? Number(conversionFactor) : 1;
  const costInclTax = costPerStockUom * factor * (1 + inclusiveTaxRate / 100);
  return { costInclTax, margin: sellPrice - costInclTax };
}

/**
 * A cost shown beside a tax-inclusive rate is shown tax-inclusive too, so the two figures can
 * be compared at a glance. `cost` is already per the selling UOM.
 */
export function getDisplayCost(cost: number, inclusiveTaxRate: number): number {
  return (Number(cost) || 0) * (1 + (Number(inclusiveTaxRate) || 0) / 100);
}
