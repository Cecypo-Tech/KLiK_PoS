/** The cashier's note on the sale: kept on a held order, written to the invoice's Remarks. */
export const REMARKS_MAX_LENGTH = 2000;

export default function RemarksInput({
  value,
  onChange,
  disabled,
  inline = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  /** Label beside the box, for the Other charges card. */
  inline?: boolean;
}) {
  const box = (
    <textarea
      id="pos-checkout-remarks"
      rows={2}
      maxLength={REMARKS_MAX_LENGTH}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      placeholder="Note for this sale"
      className="w-full resize-y rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-beveren-500 disabled:cursor-not-allowed disabled:opacity-50"
    />
  );
  if (inline) {
    return (
      <div className="flex items-start justify-between gap-3">
        <label htmlFor="pos-checkout-remarks" className="pt-1.5 text-sm font-medium text-gray-600 dark:text-gray-400">
          Remarks
        </label>
        <div className="w-2/3">{box}</div>
      </div>
    );
  }
  return (
    <div className="min-w-[12rem] flex-1 basis-full">
      <label htmlFor="pos-checkout-remarks" className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
        Remarks
      </label>
      {box}
    </div>
  );
}
