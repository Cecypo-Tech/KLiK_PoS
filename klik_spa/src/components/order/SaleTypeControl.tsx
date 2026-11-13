import type { SaleType } from "../../utils/saleType";

export interface SaleTypeControlProps {
  value: SaleType;
  /** Shown in this order. */
  options: SaleType[];
  onChange: (type: SaleType) => void;
  /** A segment with a reason is disabled, and the reason is its tooltip. */
  disabledReasons?: Partial<Record<SaleType, string>>;
  disabled?: boolean;
}

const LABEL: Record<SaleType, string> = { sale: "Sale", credit: "Credit", quote: "Quote" };
// Credit and Quote keep the colours they already had (teal credit, amber quote banner).
const SELECTED: Record<SaleType, string> = {
  sale: "bg-beveren-600 text-white",
  credit: "bg-teal-600 text-white dark:bg-teal-500",
  quote: "bg-amber-600 text-white",
};

/** What the cart is building: Sale, Credit or Quote. Nothing to choose → nothing shown. */
export default function SaleTypeControl({ value, options, onChange, disabledReasons, disabled }: SaleTypeControlProps) {
  if (options.length < 2) return null;
  return (
    <div role="radiogroup" aria-label="Sale type" className="inline-flex w-full rounded-lg bg-gray-100 dark:bg-gray-700 p-0.5 text-sm">
      {options.map((type) => {
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
            className={`flex-1 px-3 py-1 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              checked ? SELECTED[type] : "text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-600"
            }`}
          >
            {LABEL[type]}
          </button>
        );
      })}
    </div>
  );
}
