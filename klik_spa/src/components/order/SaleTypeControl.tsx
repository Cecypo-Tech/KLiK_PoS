import type { SaleType } from "../../utils/saleType";

export interface SaleTypeControlProps {
  value: SaleType;
  /** Which types this till offers; the order shown is fixed (Quote, Cash Sale, Credit Sale). */
  options: SaleType[];
  onChange: (type: SaleType) => void;
  /** An option with a reason is disabled, and the reason follows its label. */
  disabledReasons?: Partial<Record<SaleType, string>>;
  disabled?: boolean;
}

const ORDER: SaleType[] = ["quote", "sale", "credit"];
const LABEL: Record<SaleType, string> = { sale: "Cash Sale", credit: "Credit Sale", quote: "Quote" };
// The box wears the chosen type's colour: beveren sale, teal credit, amber quote (the bar turns amber too).
const COLOUR: Record<SaleType, string> = {
  sale: "bg-beveren-600 hover:bg-beveren-700",
  credit: "bg-teal-600 hover:bg-teal-700 dark:bg-teal-500",
  quote: "bg-amber-600 hover:bg-amber-700",
};

/** What the cart is building, as one dropdown. Nothing to choose → nothing shown. */
export default function SaleTypeControl({ value, options, onChange, disabledReasons, disabled }: SaleTypeControlProps) {
  if (options.length < 2) return null;
  return (
    <select
      aria-label="Sale type"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as SaleType)}
      className={`h-9 shrink-0 rounded-lg border-0 pl-3 pr-8 text-sm font-semibold text-white cursor-pointer transition-colors focus:ring-2 focus:ring-offset-1 focus:ring-beveren-400 disabled:cursor-not-allowed disabled:opacity-60 ${COLOUR[value]}`}
    >
      {ORDER.filter((t) => options.includes(t)).map((t) => (
        <option key={t} value={t} disabled={!!disabledReasons?.[t]} className="bg-white text-gray-900 font-normal">
          {disabledReasons?.[t] ? `${LABEL[t]} — ${disabledReasons[t]}` : LABEL[t]}
        </option>
      ))}
    </select>
  );
}
