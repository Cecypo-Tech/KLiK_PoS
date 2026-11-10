import { useEffect, useLayoutEffect, useRef, useState, type InputHTMLAttributes, type KeyboardEvent } from "react";
import { evaluateNumber, formatNumber, isExpression, plainNumber, readNumber, type NumberKind } from "../../utils/numberInput";

type NativeProps = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "defaultValue">;

export interface NumberFieldProps extends NativeProps {
  value: number | null | undefined;
  kind: NumberKind;
  /** Called once when the cashier leaves a changed box: the worked-out number (undefined when not one) and the raw text. */
  onCommit: (value: number | undefined, text: string) => void;
  /** Show an empty box (and the placeholder) for 0. */
  blankZero?: boolean;
  /** Enter commits and Escape reverts. Off where a parent (the line grid) owns those keys. */
  ownKeys?: boolean;
  wrapperClassName?: string;
}

/**
 * A number box that takes a sum, like ERPNext's: "4*5" becomes 20 when the cashier leaves it.
 * At rest it shows the number formatted (14,500.00); while editing, the plain number.
 */
export function NumberField({
  value, kind, onCommit, blankZero, ownKeys = true, wrapperClassName = "", className = "", onFocus, onBlur, onKeyDown, onMouseUp, readOnly, ...rest
}: NumberFieldProps) {
  const [draft, setDraft] = useState<string | null>(null);
  // A click focuses, then its mouseup drops the selection: skip that one mouseup so typing replaces the number.
  const justFocused = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const selectAll = useRef(false);
  // Select once the box shows its plain number (focus swaps 1,250.00 for 1250), before the next key lands.
  useLayoutEffect(() => {
    if (selectAll.current && document.activeElement === input.current) input.current?.select();
    selectAll.current = false;
  });
  const n = Number(value ?? 0);
  const plain = blankZero && !n ? "" : plainNumber(n);
  // Commit only what the cashier typed: a box merely visited (or reverted with Esc) sends nothing, even
  // if the line's price moved meanwhile; a number retyped as-is still sends (it clears Loss of Sale).
  const edited = useRef(false);
  const shown = draft ?? (blankZero && !n ? "" : formatNumber(n, kind));
  const result = draft !== null && isExpression(draft) ? evaluateNumber(draft) : undefined;

  // The value moved under a focused, untouched box (a price list picked, a pricing rule): show the new one.
  useEffect(() => {
    if (draft !== null && !edited.current && draft !== plain) { setDraft(plain); selectAll.current = true; }
  }, [plain]); // eslint-disable-line react-hooks/exhaustive-deps -- only when the value itself moves

  const commit = () => {
    if (draft !== null && edited.current && !readOnly) onCommit(readNumber(draft, kind), draft.trim());
    edited.current = false;
    setDraft(null);
  };

  return (
    <div className={`relative ${wrapperClassName}`}>
      <input
        {...rest}
        ref={input}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        readOnly={readOnly}
        className={`tabular-nums ${className}`}
        value={shown}
        onChange={(e) => { edited.current = true; setDraft(e.target.value); }}
        onFocus={(e) => {
          setDraft(plain);
          edited.current = false;
          justFocused.current = true;
          selectAll.current = true;
          e.currentTarget.select();
          onFocus?.(e);
        }}
        onMouseUp={(e) => {
          if (justFocused.current) e.preventDefault();
          justFocused.current = false;
          onMouseUp?.(e);
        }}
        onBlur={(e) => { commit(); onBlur?.(e); }}
        onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
          justFocused.current = false;
          onKeyDown?.(e);
          if (!ownKeys || e.defaultPrevented) return;
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") { edited.current = false; setDraft(plain); selectAll.current = true; }
        }}
      />
      {result !== undefined ? (
        <span
          aria-live="polite"
          className="pointer-events-none absolute right-1 -top-2 rounded bg-beveren-600 px-1 text-[11px] leading-4 text-white tabular-nums shadow"
        >
          = {formatNumber(result, kind === "qty" ? "qty" : "money")}
        </span>
      ) : null}
    </div>
  );
}
