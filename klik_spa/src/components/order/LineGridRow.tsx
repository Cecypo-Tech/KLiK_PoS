import { X } from "lucide-react";
import { toast } from "react-toastify";
import type { CartItem } from "../../../types";
import type { POSDetails } from "../../stores/posProfileStore";
import type { GridCol } from "../../utils/lineGridKeys";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import { getEffectiveDisplayRate, getEffectiveItemRate, getExclusiveTaxRateForItem, getPreDiscountRate, type DiscountMapLike } from "../../utils/cartPricing";
import { roundCurrency } from "../../utils/currencyMath";
import type { NumberKind } from "../../utils/numberInput";
import { NumberField } from "../ui/NumberField";
import { RatePriceField } from "./RatePriceField";
import type { PricePopupPick } from "../../utils/priceOptions";
import { useEffect, useState } from "react";
import { switchUom, uomMaps, type UomMaps } from "../../utils/uomSwitch";
import { getItemDisplayName } from "../../utils/itemDisplayName";
import { rateBoxMinimum } from "../../utils/priceFloor";
import { clampRateToFloor, discountAmountFromPct, discountPctFromAmount } from "../../utils/lineEdits";

const round2 = (n: number) => Math.round(n * 100) / 100;
const CELL = "w-full bg-transparent px-1.5 py-1 text-right tabular-nums rounded focus:outline-none focus:ring-2 focus:ring-beveren-500 read-only:text-gray-500";

const KIND: Record<Exclude<GridCol, "item">, NumberKind> = { qty: "qty", rate: "money", disc: "percent" };

/** A number cell: formatted at rest, takes a sum ("4*5"), commits once on blur (Enter/Tab/arrows blur it by moving focus). */
function NumCell({ row, col, value, readOnly, onCommit }: {
  row: number; col: Exclude<GridCol, "item">; value: number; readOnly?: boolean; onCommit: (n: number | undefined, text: string) => void;
}) {
  return (
    <NumberField
      data-row={row}
      data-col={col}
      kind={KIND[col]}
      value={value}
      readOnly={readOnly}
      ownKeys={false}
      className={CELL}
      onCommit={onCommit}
    />
  );
}

/** The line's unit: plain text, or a picker once the item is sold in more than one. */
function UomCell({ item, customerId, onUOMChange }: {
  item: CartItem; customerId?: string; onUOMChange: LineGridRowProps["onUOMChange"];
}) {
  const [maps, setMaps] = useState<UomMaps | null>(null);
  const code = item.item_code || item.id;
  useEffect(() => {
    let live = true;
    const customer = customerId ? `&customer=${encodeURIComponent(customerId)}` : "";
    fetch(`/api/method/klik_pos.api.item.item_details.get_item_uoms_and_prices?item_code=${encodeURIComponent(code)}${customer}`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => { if (live) setMaps(uomMaps(d?.message || {})); })
      .catch(() => {}); // no list: the cell stays plain text
    return () => { live = false; };
  }, [code, customerId]);

  const uom = item.uom || "";
  if (!maps || maps.uoms.length < 2) return <span className="block truncate text-gray-600 dark:text-gray-300">{uom}</span>;
  return (
    <select
      aria-label={`Unit for ${item.name}`}
      value={uom}
      onChange={(e) => {
        const next = switchUom(maps, uom, item.price, e.target.value);
        onUOMChange(item.id, next.uom, next.price, next.conversionFactor);
      }}
      className="w-full h-7 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-1 text-[13px] text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-beveren-500"
    >
      {(maps.uoms.includes(uom) ? maps.uoms : [uom, ...maps.uoms]).map((u) => <option key={u} value={u}>{u}</option>)}
    </select>
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
  onUOMChange: (itemId: string, uom: string, price: number, conversionFactor?: number) => void;
  customerId?: string;
  /** The list the cart sells on: a line on another list gets a chip by its rate. */
  cartPriceList?: string;
  currencySymbol: string;
  posDetails: POSDetails | null;
}

export default function LineGridRow({
  item, row, itemDiscount, selected, onSelect, onUpdateQuantity, onCustomRateChange, onDiscountChange, onRemoveItem,
  onUOMChange, customerId, cartPriceList, currencySymbol, posDetails,
}: LineGridRowProps) {
  // Same pricing inputs as CartItemRow, so the grid and the cart show and commit identical numbers.
  const tip = posDetails?.is_tax_included_in_basic_rate;
  const isTaxIncludedInBasicRate = tip === 1 || tip === "1" || tip === true;
  const opts = { itemDiscounts: { [item.id]: itemDiscount }, isTaxIncludedInBasicRate };
  const discountedPrice = getEffectiveItemRate(item, opts);
  // The Rate cell and the % are of the line's rate before its discount (a custom rate, else the price).
  const preOpts = { ...opts, itemDiscounts: { [item.id]: { ...itemDiscount, discountAmount: 0 } } };
  const preDiscountPrice = getPreDiscountRate(item, opts);
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
    // A typed rate is no list's price: the line drops its list (the invoice records the list it was priced from).
    if (itemDiscount.selectedPriceList) onDiscountChange(item.id, "selectedPriceList", "");
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
  // '*' in Rate: a price list sets its rate and becomes the line's list, as the panel's picker does.
  const pickPrice = (p: PricePopupPick) => {
    if (!("priceList" in p)) return commitRate(p.rate, String(p.rate));
    onDiscountChange(item.id, "selectedPriceList", p.priceList);
    onCustomRateChange(item, p.rate, false);
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
      <td className="w-24 px-1" data-uom-cell={item.id}><UomCell item={item} customerId={customerId} onUOMChange={onUOMChange} /></td>
      <td className="w-44 px-1">
        <div className="flex items-center gap-1">
        <RatePriceField
          data-row={row}
          data-col="rate"
          item={item}
          warehouse={posDetails?.warehouse || ""}
          allowRateChange={!!Number(posDetails?.allow_rate_change)}
          allowPriceLists={!!Number(posDetails?.allow_price_list_switching)}
          activeList={itemDiscount.selectedPriceList}
          currencySymbol={currencySymbol}
          value={round2(editableRate)}
          readOnly={!Number(posDetails?.allow_rate_change)}
          ownKeys={false}
          className={CELL}
          wrapperClassName="flex-1 min-w-0"
          onCommit={commitRate}
          onPick={pickPrice}
        />
          {itemDiscount.selectedPriceList && itemDiscount.selectedPriceList !== cartPriceList ? (
            <span
              data-price-chip={item.id}
              title={`Price list: ${itemDiscount.selectedPriceList}`}
              className="shrink-0 max-w-[5.5rem] truncate rounded-full bg-beveren-100 ring-1 ring-beveren-300 dark:bg-beveren-900/40 dark:ring-beveren-700 px-1.5 py-0.5 text-[11px] font-medium text-beveren-700 dark:text-beveren-300"
            >{itemDiscount.selectedPriceList}</span>
          ) : null}
        </div>
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
