import type { SaleType } from "../../utils/saleType";

export interface SaleTypeControlProps {
  value: SaleType;
  /** Which types this till offers; the layout order is fixed (Quote, then Cash Sale | Credit Sale). */
  options: SaleType[];
  onChange: (type: SaleType) => void;
  /** A segment with a reason is disabled, and the reason is its tooltip. */
  disabledReasons?: Partial<Record<SaleType, string>>;
  disabled?: boolean;
}

const LABEL: Record<SaleType, string> = { sale: "Cash Sale", credit: "Credit Sale", quote: "Quote" };
// Credit and Quote keep the colours they already had (teal credit, amber quote banner).
const SELECTED: Record<SaleType, string> = {
  sale: "bg-beveren-600 text-white",
  credit: "bg-teal-600 text-white dark:bg-teal-500",
  quote: "bg-amber-600 text-white",
};

/** What the cart is building: Quote on its own, then the Cash Sale | Credit Sale switch.
 * Nothing to choose → nothing shown. */
export default function SaleTypeControl({ value, options, onChange, disabledReasons, disabled }: SaleTypeControlProps) {
  if (options.length < 2) return null;
  const segment = (type: SaleType, shape: string) => {
    const reason = disabledReasons?.[type];
    const checked = type === value;
    return (
      <button
        key={type}
        type="button"
        role="radio"
        aria-checked={checked}
        title={reason}
        disabled={disabled || !!reason}
        onClick={() => !checked && onChange(type)}
        className={`${shape} px-3 py-1 font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          checked ? SELECTED[type] : "text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-600"
        }`}
      >
        {LABEL[type]}
      </button>
    );
  };
  const pays = (["sale", "credit"] as const).filter((t) => options.includes(t));
  return (
    <div role="radiogroup" aria-label="Sale type" className="inline-flex items-center gap-4 text-sm">
      {options.includes("quote") && (
        <div className="inline-flex rounded-lg bg-gray-100 dark:bg-gray-700 p-0.5">{segment("quote", "rounded-md")}</div>
      )}
      {pays.length > 0 && (
        <div className="inline-flex rounded-lg bg-gray-100 dark:bg-gray-700 p-0.5">{pays.map((t) => segment(t, "rounded-md"))}</div>
      )}
    </div>
  );
}
