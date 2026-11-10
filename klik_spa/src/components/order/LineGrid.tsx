import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { CartItem, MenuItem } from "../../../types";
import type { POSDetails } from "../../stores/posProfileStore";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import type { DiscountMapLike } from "../../utils/cartPricing";
import { gridKeyAction, type GridCol } from "../../utils/lineGridKeys";
import { toast } from "react-toastify";
import { exactCodeMatch, highlightRanges, latestOnly, scanAdd, searchGridItems, STALE } from "../../utils/lineGridSearch";
import LineGridRow from "./LineGridRow";

export interface LineGridProps {
  items: CartItem[];
  itemDiscounts: DiscountMapLike;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUpdateQuantity: (id: string, qty: number) => void;
  onCustomRateChange: (item: CartItem, rate?: number, includesTax?: boolean) => void;
  onDiscountChange: (itemId: string, field: string, value: number | string) => void;
  onRemoveItem: (id: string) => void;
  onUOMChange: (itemId: string, uom: string, price: number, conversionFactor?: number) => void;
  /** Customer-specific unit prices in the UOM picker. */
  customerId?: string;
  onOpenDescription: (id: string) => void;
  /** OrderSummary routes variants/templates to the existing picker; null = no line was made. */
  onPickItem: (item: MenuItem) => Promise<string | null>;
  currencySymbol: string;
  posDetails: POSDetails | null;
}

export interface LineGridHandle {
  focusEntry: () => void;
}

/** Where focus goes once React has rendered: a display position, or a line by id (its row may not exist yet). */
type PendingFocus = { row: number; col: GridCol } | { id: string; col: GridCol };

function Highlight({ text, query }: { text: string; query: string }) {
  const parts: ReactNode[] = [];
  let at = 0;
  for (const [a, b] of highlightRanges(text, query)) {
    parts.push(text.slice(at, a), <mark key={a} className="bg-yellow-200 dark:bg-yellow-700/60 text-inherit">{text.slice(a, b)}</mark>);
    at = b;
  }
  parts.push(text.slice(at));
  return <>{parts}</>;
}

const LineGrid = forwardRef<LineGridHandle, LineGridProps>(function LineGrid(props, ref) {
  const { items, itemDiscounts, selectedId, onSelect, onRemoveItem, onOpenDescription, onPickItem, currencySymbol, posDetails } = props;
  const tableRef = useRef<HTMLTableElement>(null);
  const pending = useRef<PendingFocus | null>(null);
  const busy = useRef(false); // a double Enter must not add twice
  const latest = useRef(latestOnly<MenuItem[]>());
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MenuItem[]>([]);
  const [highlight, setHighlight] = useState(0);
  const [open, setOpen] = useState(false);

  const top = posDetails?.custom_cart_item_insertion_position === "Top";
  const entryRow = top ? 0 : items.length;
  const rowCount = items.length + 1;
  const lineAt = (row: number) => items[top ? row - 1 : row];
  const rowOf = (index: number) => (top ? index + 1 : index);

  const focusCell = (row: number, col: GridCol): boolean => {
    const el = tableRef.current?.querySelector<HTMLElement>(`[data-row="${row}"][data-col="${col}"]`);
    el?.focus();
    return !!el;
  };

  const flushFocus = () => {
    const p = pending.current;
    if (!p) return;
    if ("row" in p) {
      focusCell(p.row, p.col); // one try only, on the render after the delete; never steal focus later
      pending.current = null;
      return;
    }
    const index = items.findIndex((i) => i.id === p.id);
    if (index >= 0 && focusCell(rowOf(index), p.col)) pending.current = null;
  };
  // Runs after every render: deletes and picks change `items`, and the target cell only exists afterwards.
  useLayoutEffect(flushFocus);

  // By the entry row's own marker, not its index: after an awaited add the index captured by this
  // render's closures is stale (the new line takes it when lines land at the bottom).
  const focusEntry = () => tableRef.current?.querySelector<HTMLElement>("[data-entry-row] input")?.focus();
  useImperativeHandle(ref, () => ({ focusEntry }), []);
  useEffect(() => { focusEntry(); }, []); // grid mode opens ready to scan

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      void latest.current(Promise.resolve([])); // makes any in-flight search stale
      setResults([]);
      setOpen(false);
      return;
    }
    const t = setTimeout(() => {
      latest.current(searchGridItems(q))
        .then((r) => {
          if (r === STALE) return;
          setResults(r);
          setHighlight(0);
          setOpen(r.length > 0);
        })
        .catch((e) => console.error("Grid item search failed:", e));
    }, 150);
    return () => clearTimeout(t);
  }, [query]);

  // Clears the entry only if it still holds what was submitted: a second scan may be typing in it.
  const clearEntry = (q: string) => setQuery((cur) => (cur.trim() === q ? "" : cur));

  /** `then`: focus the new line's Qty (a picked result) or go back to the entry (a scan). */
  const pick = async (item: MenuItem | undefined, then: "qty" | "entry" = "qty") => {
    if (!item) return;
    const q = query.trim();
    setOpen(false);
    const lineId = await onPickItem(item);
    if (!lineId) {
      focusEntry(); // refused, or the variant picker took over: keep the typed text
      return;
    }
    clearEntry(q);
    if (then === "entry") return void focusEntry();
    pending.current = { id: lineId, col: "qty" };
    flushFocus();
  };

  const submitEntry = async () => {
    const q = query.trim();
    if (!q || busy.current) return;
    busy.current = true;
    try {
      let r;
      try {
        r = await scanAdd(q, { quiet: true }); // a miss may still be an item code or a pick; toasted below
      } catch (e) {
        console.error("Grid scan failed:", e); // leave the text so the cashier can retry
        return;
      }
      if ("lineId" in r) {
        clearEntry(q);
        focusEntry();
        return;
      }
      if ("pick" in r) return void (await pick(r.pick, "entry")); // a variant template: the picker
      if (!("notFound" in r)) return; // refused: the cart said why
      // An exact item code is a scan; the highlighted result only once the cashier moved off the top.
      let exact = highlight === 0 ? exactCodeMatch(results, q) : undefined;
      if (!results.length) exact = exactCodeMatch(await searchGridItems(q).catch(() => []), q);
      if (exact) return void (await pick(exact, "entry"));
      if (results.length) return void (await pick(results[highlight]));
      toast.error(`No item found for ${q}`);
    } finally {
      busy.current = false;
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTableElement>) => {
    const target = e.target as HTMLElement;
    const col = target.dataset.col as GridCol | undefined;
    const row = Number(target.dataset.row);
    if (!col || Number.isNaN(row)) return;
    const action = gridKeyAction({
      key: e.key, shift: e.shiftKey, ctrl: e.ctrlKey, alt: e.altKey,
      col, row, rowCount, entryRow,
      dropdownOpen: open && row === entryRow, rowEmpty: false,
      editable: {
        rate: !!Number(posDetails?.allow_rate_change),
        disc: !!Number(posDetails?.allow_discount_change),
        uom: !!tableRef.current?.querySelector(`[data-row="${row}"][data-col="uom"]`), // a picker only when the item has units to pick
      },
    });
    if (action.type === "none") return;
    e.preventDefault();
    switch (action.type) {
      // A row with one unit has no UOM stop: up/down from a UOM lands on that row's qty.
      case "focus": return void (focusCell(action.row, action.col) || (action.col === "uom" && focusCell(action.row, "qty")));
      case "commit": return void (focusCell(action.then.row, action.then.col) || (action.then.col === "uom" && focusCell(action.then.row, "qty"))); // the cell commits on blur
      // Enter still tries an exact scan first (submitEntry falls back to the highlighted result); Tab picks.
      case "pickHighlighted": return void (e.key === "Enter" ? submitEntry() : pick(results[highlight]));
      case "moveHighlight": return setHighlight((h) => Math.min(results.length - 1, Math.max(0, h + action.delta)));
      case "closeDropdown": return setOpen(false);
      case "submitEntry": return void submitEntry();
      case "openDescription": { const l = lineAt(action.row); if (l) onOpenDescription(l.id); return; }
      case "deleteRow": {
        const l = lineAt(action.row);
        if (!l) return;
        pending.current = action.then; // a post-deletion index: applied once the line is gone
        onRemoveItem(l.id);
      }
    }
  };

  const entry = (
    <tr data-entry-row="" className="border-b border-gray-100 dark:border-gray-800">
      <td className="relative px-2 py-1" colSpan={7}>
        <input
          type="text"
          data-row={entryRow}
          data-col="item"
          value={query}
          placeholder="Scan or type an item…"
          autoComplete="off"
          onChange={(e) => {
            setQuery(e.target.value);
            void latest.current(Promise.resolve([])); // an in-flight search for the old text is now stale
            setResults([]); // only results for the current text may be picked
            setOpen(false);
          }}
          onBlur={() => setOpen(false)}
          onFocus={() => results.length && query.trim() && setOpen(true)}
          className="w-full rounded px-1.5 py-1 bg-transparent focus:outline-none focus:ring-2 focus:ring-beveren-500"
        />
        {open ? (
          <ul role="listbox" className="absolute left-2 z-30 mt-1 w-[28rem] max-w-[90vw] rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
            {results.map((r, i) => (
              <li
                key={r.id}
                role="option"
                aria-selected={i === highlight}
                onMouseDown={(e) => { e.preventDefault(); void pick(r); }}
                onMouseEnter={() => setHighlight(i)}
                className={`flex h-7 items-center gap-2 px-2 cursor-pointer ${i === highlight ? "bg-beveren-50 dark:bg-beveren-900/30" : ""}`}
              >
                <span className="min-w-0 flex-1 truncate text-gray-900 dark:text-white"><Highlight text={r.name} query={query.trim()} /></span>
                <span className="truncate font-mono text-[11px] text-gray-400">{r.item_code || r.id}</span>
                <span className="tabular-nums text-gray-700 dark:text-gray-300">{formatCurrencyWithSymbol(r.price, currencySymbol)}</span>
                <span className={`w-12 text-right tabular-nums ${r.available > 0 ? "text-green-600" : "text-red-600"}`}>{r.available}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </td>
    </tr>
  );

  return (
    <table ref={tableRef} onKeyDown={onKeyDown} className="w-full table-fixed text-[13px]">
      <thead>
        <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
          <th className="px-2 py-1 text-left font-medium">Item</th>
          <th className={`${Number(posDetails?.custom_enable_loss_of_sale) ? "w-32" : "w-20"} px-2 py-1 text-right font-medium`}>Qty</th>
          <th className="w-24 px-2 py-1 text-left font-medium">UOM</th>
          <th className="w-28 px-2 py-1 text-right font-medium">Rate</th>
          <th className="w-20 px-2 py-1 text-right font-medium">Disc %</th>
          <th className="w-28 px-2 py-1 text-right font-medium">Total</th>
          <th className="w-8" />
        </tr>
      </thead>
      <tbody>
        {top ? entry : null}
        {items.map((item, index) => (
          <LineGridRow
            key={item.id}
            item={item}
            row={rowOf(index)}
            itemDiscount={itemDiscounts[item.id] || {}}
            selected={item.id === selectedId}
            onSelect={onSelect}
            onUpdateQuantity={props.onUpdateQuantity}
            onCustomRateChange={props.onCustomRateChange}
            onDiscountChange={props.onDiscountChange}
            onRemoveItem={onRemoveItem}
            onUOMChange={props.onUOMChange}
            customerId={props.customerId}
            currencySymbol={currencySymbol}
            posDetails={posDetails}
          />
        ))}
        {top ? null : entry}
      </tbody>
    </table>
  );
});

export default LineGrid;
