import { SALE_TYPE_COLOUR, SALE_TYPE_LABEL, type SaleType } from "../../utils/saleType";

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
/** What the cart is building, as one dropdown. Nothing to choose → nothing shown. */
export default function SaleTypeControl({ value, options, onChange, disabledReasons, disabled }: SaleTypeControlProps) {
  if (options.length < 2) return null;
  return (
    <select
      aria-label="Sale type"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as SaleType)}
      className={`h-9 shrink-0 rounded-lg border-0 pl-3 pr-8 text-sm font-semibold text-white cursor-pointer transition-colors focus:ring-2 focus:ring-offset-1 focus:ring-beveren-400 disabled:cursor-not-allowed disabled:opacity-60 ${SALE_TYPE_COLOUR[value]}`}
    >
      {ORDER.filter((t) => options.includes(t)).map((t) => (
        <option key={t} value={t} disabled={!!disabledReasons?.[t]} className="bg-white text-gray-900 font-normal">
          {disabledReasons?.[t] ? `${SALE_TYPE_LABEL[t]} — ${disabledReasons[t]}` : SALE_TYPE_LABEL[t]}
        </option>
      ))}
    </select>
  );
}
