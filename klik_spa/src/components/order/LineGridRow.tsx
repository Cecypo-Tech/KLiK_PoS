import { useState } from "react";
import { X } from "lucide-react";
import { toast } from "react-toastify";
import type { CartItem } from "../../../types";
import type { POSDetails } from "../../stores/posProfileStore";
import type { GridCol } from "../../utils/lineGridKeys";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import { getEffectiveDisplayRate, getEffectiveItemRate, getExclusiveTaxRateForItem, type DiscountMapLike } from "../../utils/cartPricing";
import { roundCurrency } from "../../utils/currencyMath";
import { getItemDisplayName } from "../../utils/itemDisplayName";
import { rateBoxMinimum } from "../../utils/priceFloor";
import { clampRateToFloor, discountAmountFromPct, discountPctFromAmount, parseDecimalInput } from "../../utils/lineEdits";

const round2 = (n: number) => Math.round(n * 100) / 100;
const CELL = "w-full bg-transparent px-1.5 py-1 text-right tabular-nums rounded focus:outline-none focus:ring-2 focus:ring-beveren-500 read-only:text-gray-500";

/** A number cell: shows `value`, edits as text, commits once on blur (Enter/Tab/arrows blur it by moving focus). */
function NumCell({ row, col, value, readOnly, onCommit }: {
  row: number; col: GridCol; value: number; readOnly?: boolean; onCommit: (n: number | undefined, text: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <input
      type="text"
      inputMode="decimal"
      data-row={row}
      data-col={col}
      readOnly={readOnly}
      className={CELL}
      value={draft ?? String(value)}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={(e) => { setDraft(String(value)); e.currentTarget.select(); }}
      onBlur={() => {
        if (draft !== null && !readOnly && draft !== String(value)) onCommit(parseDecimalInput(draft), draft.trim());
        setDraft(null);
      }}
    />
  );
}

interface LineGridRowProps {
  item: CartItem;
  row: number;
  itemDiscount: NonNullable<DiscountMapLike[string]>;
  selected: boolean;
  onSelect: (id: string) => void;
  onUpdateQuantity: (id: string, qty: number) => void;
  onCustomRateChange: (item: CartItem, rate?: number, includesTax?: boolean) => void;
  onDiscountChange: (itemId: string, field: string, value: number | string) => void;
  onRemoveItem: (id: string) => void;
  currencySymbol: string;
  posDetails: POSDetails | null;
}

export default function LineGridRow({
  item, row, itemDiscount, selected, onSelect, onUpdateQuantity, onCustomRateChange, onDiscountChange, onRemoveItem,
  currencySymbol, posDetails,
}: LineGridRowProps) {
  // Same pricing inputs as CartItemRow, so the grid and the cart show and commit identical numbers.
  const tip = posDetails?.is_tax_included_in_basic_rate;
  const isTaxIncludedInBasicRate = tip === 1 || tip === "1" || tip === true;
  const opts = { itemDiscounts: { [item.id]: itemDiscount }, isTaxIncludedInBasicRate };
  const discountedPrice = getEffectiveItemRate(item, opts);
  // The Rate cell and the % are of the line's rate before its discount (a custom rate, else the price).
  const preOpts = { ...opts, itemDiscounts: { [item.id]: { ...itemDiscount, discountAmount: 0 } } };
  const preDiscountPrice = getEffectiveItemRate(item, preOpts);
  const hasExclusiveTax = getExclusiveTaxRateForItem(item, { isTaxIncludedInBasicRate }) > 0;
  const editableRate = hasExclusiveTax ? preDiscountPrice : getEffectiveDisplayRate(item, preOpts);
  const total = roundCurrency(discountedPrice * item.quantity);
  const discPct = discountPctFromAmount(preDiscountPrice, Number(itemDiscount.discountAmount || 0));
  const listRate = Number(item.original_price || 0) || item.price;

  const commitQty = (n: number | undefined) => {
    if (n !== undefined && Number.isFinite(n) && n > 0 && n !== item.quantity) onUpdateQuantity(item.id, n);
  };
  // As CartItemRow.handleRateChange: empty resets to the list rate; any rate change clears the line discount.
  const commitRate = (n: number | undefined, text: string) => {
    if (n === undefined && text !== "") return;
    if (n === undefined) {
      onCustomRateChange(item, undefined);
    } else {
      // ponytail: floor uses the list rate; CartItemRow also honours a line price-list pick fetched on expand.
      const minimum = rateBoxMinimum(posDetails as Record<string, unknown> | null, listRate);
      const rate = clampRateToFloor(Math.max(0, n), minimum);
      if (rate !== Math.max(0, n)) {
        toast.warning(`${item.name}: can't sell below ${formatCurrencyWithSymbol(rate, currencySymbol)}. Rate reset to the minimum.`);
      }
      onCustomRateChange(item, rate, isTaxIncludedInBasicRate);
    }
    onDiscountChange(item.id, "discountAmount", 0);
  };
  const commitDisc = (n: number | undefined) => {
    if (n !== undefined) onDiscountChange(item.id, "discountAmount", discountAmountFromPct(preDiscountPrice, n));
  };

  return (
    <tr
      data-line-id={item.id}
      onClick={() => onSelect(item.id)}
      onFocus={() => onSelect(item.id)}
      className={`border-b border-gray-100 dark:border-gray-800 ${selected ? "bg-beveren-50 dark:bg-beveren-900/20" : ""}`}
    >
      <td className="px-2 py-1">
        <div tabIndex={0} data-row={row} data-col="item" className="rounded px-1 focus:outline-none focus:ring-2 focus:ring-beveren-500">
          <div className="truncate text-gray-900 dark:text-white" title={item.name}>
            {getItemDisplayName(item, !!posDetails?.custom_use_item_code_as_display_name)}
          </div>
          {item.description ? (
            <div className="truncate text-xs italic text-gray-500 dark:text-gray-400">{item.description}</div>
          ) : null}
        </div>
      </td>
      <td className="w-20 px-1"><NumCell row={row} col="qty" value={item.quantity} onCommit={commitQty} /></td>
      <td className="w-28 px-1">
        <NumCell row={row} col="rate" value={round2(editableRate)} readOnly={!Number(posDetails?.allow_rate_change)} onCommit={commitRate} />
      </td>
      <td className="w-20 px-1">
        <NumCell row={row} col="disc" value={round2(discPct)} readOnly={!Number(posDetails?.allow_discount_change)} onCommit={commitDisc} />
      </td>
      <td className="w-28 px-2 text-right font-semibold tabular-nums whitespace-nowrap text-beveren-600 dark:text-beveren-400">
        {formatCurrencyWithSymbol(total, currencySymbol)}
      </td>
      <td className="w-8 text-center">
        <button
          type="button"
          tabIndex={-1}
          aria-label="Remove line"
          onClick={(e) => { e.stopPropagation(); onRemoveItem(item.id); }}
          className="rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
        >
          <X size={14} />
        </button>
      </td>
    </tr>
  );
}
