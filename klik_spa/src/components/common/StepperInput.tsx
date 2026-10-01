import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { stepValue } from "../../utils/stepValue";

/** Hides the browser's own spin buttons: tiny, hugging the digits, and doubling up beside
 * a field's own -/+ or arrow buttons. */
export const NO_NATIVE_SPINNER =
  "[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";

interface StepperInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Called with the new value when an arrow is pressed. Typing still goes through onChange. */
  onStep: (next: number) => void;
  /** What one arrow press adds or takes away. Whole units by default - a money field's
   * arrows are for nudging by a shilling; the keyboard keeps the input's own fine step. */
  stepBy?: number;
  minValue?: number;
  maxValue?: number;
  /** Width and layout of the whole control (the input fills it). */
  wrapperClassName?: string;
}

/**
 * A number field with its own up/down arrows. The browser's spin buttons are tiny, hug the
 * digits and cannot be spaced; these sit apart from the number behind a divider, with a
 * larger hit area. They keep focus in the field and stay out of the tab order - the arrow
 * keys already step a number input.
 */
const StepperInput = forwardRef<HTMLInputElement, StepperInputProps>(function StepperInput(
  { onStep, stepBy = 1, minValue = 0, maxValue, wrapperClassName = "", className = "", disabled, value, ...rest },
  ref,
) {
  const name = (rest["aria-label"] as string | undefined) || (rest.placeholder as string | undefined) || "value";
  const locked = disabled || rest.readOnly;
  const step = (direction: 1 | -1) =>
    onStep(stepValue((value as number | string | undefined) ?? 0, direction, stepBy, minValue, maxValue));

  const arrow =
    "flex flex-1 items-center justify-center text-gray-500 dark:text-gray-400 transition-colors hover:bg-gray-100 hover:text-beveren-600 dark:hover:bg-gray-700 dark:hover:text-beveren-400 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className={`relative ${wrapperClassName}`}>
      <input
        ref={ref}
        type="number"
        value={value}
        disabled={disabled}
        {...rest}
        className={`${className} pr-10 ${NO_NATIVE_SPINNER}`}
      />
      <div className="absolute inset-y-1 right-1 flex w-7 flex-col overflow-hidden border-l border-gray-200 dark:border-gray-600">
        <button
          type="button"
          tabIndex={-1}
          aria-label={`Increase ${name}`}
          disabled={locked}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => step(1)}
          className={`${arrow} rounded-tr-md`}
        >
          <ChevronUp size={14} />
        </button>
        <button
          type="button"
          tabIndex={-1}
          aria-label={`Decrease ${name}`}
          disabled={locked}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => step(-1)}
          className={`${arrow} rounded-br-md`}
        >
          <ChevronDown size={14} />
        </button>
      </div>
    </div>
  );
});

export default StepperInput;
