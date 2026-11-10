import { useState } from "react";
import type { CartItem } from "../../../types";
import PriceListPopup from "../PriceListPopup";
import { NumberField, type NumberFieldProps } from "../ui/NumberField";
import {
  computePricePopupPosition, openPricePopupState, pricePopupKey, starOpensPricePopup,
  type PricePopupPick, type PricePopupPosition, type PricePopupState,
} from "../../utils/priceOptions";

interface RatePriceFieldProps extends Omit<NumberFieldProps, "kind"> {
  item: CartItem;
  warehouse: string;
  /** posDetails.allow_rate_change: the Custom row. */
  allowRateChange: boolean;
  /** posDetails.allow_price_list_switching: the price-list rows. */
  allowPriceLists: boolean;
  /** The line's chosen price list, highlighted when the popup opens. */
  activeList?: string;
  currencySymbol: string;
  onPick: (pick: PricePopupPick) => void;
}

/** The Rate box: takes a sum like any number box, and '*' as its first key opens the
 * item's price lists (the item list's '*' popup) - arrows choose, digits type a custom price. */
export function RatePriceField({
  item, warehouse, allowRateChange, allowPriceLists, activeList, currencySymbol, onPick, onKeyDown, onBlur, value, readOnly, ...rest
}: RatePriceFieldProps) {
  const [popup, setPopup] = useState<(PricePopupState & { position: PricePopupPosition }) | null>(null);

  const open = async (input: HTMLInputElement) => {
    if (!allowPriceLists) return;
    try {
      const res = await fetch(
        `/api/method/klik_pos.api.item.item_details.get_full_pricing_and_batch_details?item_code=${encodeURIComponent(item.item_code || item.id)}&warehouse=${encodeURIComponent(warehouse)}`,
        { credentials: "include" },
      );
      const all: { price_list: string; rate: number; uom?: string }[] = (await res.json())?.message?.price_lists || [];
      // As the cart's own price-list UI: a list in another unit, or at 0, is no price for this line.
      const lists = all.filter((p) => (!p.uom || p.uom === item.uom) && Number(p.rate || 0) > 0);
      if (!lists.length || document.activeElement !== input) return; // nothing to choose, or the cashier moved on
      const state = openPricePopupState(lists, allowRateChange, Number(value) || 0, activeList);
      setPopup({ ...state, position: computePricePopupPosition(input.getBoundingClientRect(), state.options.length, { width: window.innerWidth, height: window.innerHeight }) });
    } catch (error) {
      console.error("Could not load price lists:", error);
    }
  };

  const apply = (r: ReturnType<typeof pricePopupKey>) => {
    setPopup(r.state && popup ? { ...r.state, position: popup.position } : null);
    if (r.pick) onPick(r.pick);
  };

  return (
    <>
      <NumberField
        {...rest}
        kind="money"
        value={value}
        readOnly={readOnly}
        aria-haspopup="listbox"
        aria-expanded={!!popup}
        onKeyDown={(e) => {
          if (popup) {
            const r = pricePopupKey(popup, e.key);
            if (r.handled) { e.preventDefault(); e.stopPropagation(); }
            apply(r);
            return;
          }
          const el = e.currentTarget;
          if (!readOnly && starOpensPricePopup(e.key, el.value, el.selectionStart, el.selectionEnd)) {
            e.preventDefault();
            e.stopPropagation();
            void open(el);
            return;
          }
          onKeyDown?.(e);
        }}
        onBlur={(e) => { setPopup(null); onBlur?.(e); }}
      />
      {popup ? (
        <PriceListPopup
          options={popup.options}
          selectedIndex={popup.selectedIndex}
          customValue={popup.customValue}
          customValueSelected={popup.customSelected}
          position={popup.position}
          currencySymbol={currencySymbol}
          onSelect={(index) => apply(pricePopupKey({ ...popup, selectedIndex: index }, "Enter"))}
        />
      ) : null}
    </>
  );
}
