import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import { useDeliveryPersonnel, type DeliveryPersonnel } from "../../hooks/useDeliveryPersonnel";
import { filterOptions, moveHighlight } from "../../utils/filterOptions";

interface DeliveryPersonnelComboboxProps {
  value: string | null;
  onChange: (name: string | null) => void;
  disabled?: boolean;
  className?: string;
}

const label = (person: DeliveryPersonnel) => person.delivery_personnel || person.name;

/**
 * Type to filter, pick with a click or the arrow keys and Enter. Replaces a modal that listed
 * every delivery person in one unscrollable column - a shop with dozens could not reach
 * the ones below the fold. It sits at the bottom of the checkout, so the list opens upward.
 */
export default function DeliveryPersonnelCombobox({ value, onChange, disabled, className = "" }: DeliveryPersonnelComboboxProps) {
  const { personnel, loading, error } = useDeliveryPersonnel();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(-1);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedLabel = useMemo(() => {
    if (!value) return "";
    const person = personnel.find((p) => p.name === value);
    return person ? label(person) : value;
  }, [personnel, value]);

  const matches = useMemo(() => filterOptions(personnel, query, label, (p) => p.name), [personnel, query]);

  useEffect(() => {
    setHighlight(matches.length ? 0 : -1);
  }, [matches]);

  useEffect(() => {
    if (!open || highlight < 0) return;
    const item = listRef.current?.children[highlight] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlight, open]);

  const choose = (person: DeliveryPersonnel) => {
    onChange(person.name);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setHighlight((current) => moveHighlight(current, matches.length, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Enter") {
      if (open && highlight >= 0 && matches[highlight]) {
        event.preventDefault();
        choose(matches[highlight]);
      }
    } else if (event.key === "Escape") {
      if (open) {
        // Close the list only; the checkout's own Escape must not fire too.
        event.preventDefault();
        event.stopPropagation();
        event.nativeEvent.stopImmediatePropagation();
        setOpen(false);
        setQuery("");
      }
    }
  };

  return (
    <div className={`relative ${className}`}>
      <div className="flex items-center rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus-within:ring-2 focus-within:ring-beveren-500">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls="delivery-personnel-options"
          aria-autocomplete="list"
          disabled={disabled}
          // While searching, the current choice stays in view as the hint.
          placeholder={selectedLabel || "Select Delivery Personnel"}
          value={open ? query : selectedLabel}
          onFocus={() => {
            setQuery("");
            setOpen(true);
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          // Let a click on an option land before the list closes.
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          className="w-full min-w-0 bg-transparent px-4 py-2 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        />
        {value && !disabled ? (
          <button
            type="button"
            aria-label="Clear delivery personnel"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              onChange(null);
              setQuery("");
            }}
            className="px-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X size={16} />
          </button>
        ) : (
          <ChevronDown size={16} className="mr-3 flex-shrink-0 text-gray-400 dark:text-gray-500" />
        )}
      </div>

      {open && !disabled && (
        <ul
          id="delivery-personnel-options"
          ref={listRef}
          role="listbox"
          className="absolute bottom-full left-0 z-50 mb-1 max-h-64 w-full min-w-[14rem] overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 py-1 shadow-lg"
        >
          {loading ? (
            <li className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">Loading delivery personnel...</li>
          ) : error ? (
            <li className="px-4 py-2 text-sm text-red-500 dark:text-red-400">{error}</li>
          ) : matches.length === 0 ? (
            <li className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
              {personnel.length ? `No one matches "${query.trim()}"` : "No delivery personnel found"}
            </li>
          ) : (
            matches.map((person, index) => (
              <li
                key={person.name}
                role="option"
                aria-selected={person.name === value}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => choose(person)}
                className={`cursor-pointer px-4 py-2 text-sm text-gray-900 dark:text-white ${
                  index === highlight ? "bg-beveren-50 dark:bg-gray-700" : ""
                } ${person.name === value ? "font-semibold" : ""}`}
              >
                {label(person)}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
