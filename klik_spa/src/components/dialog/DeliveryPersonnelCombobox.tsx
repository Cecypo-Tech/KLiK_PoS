import { useEffect, useId, useMemo, useRef, useState } from "react";
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
 * Not components/ui/AutoComplete: that one renders into body, and the checkout's own
 * Escape (close the dialog) must not fire while this list is open.
 */
export default function DeliveryPersonnelCombobox({ value, onChange, disabled, className = "" }: DeliveryPersonnelComboboxProps) {
  const { personnel, loading, error } = useDeliveryPersonnel();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(-1);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listId = useId();
  const showing = open && !disabled;

  const selectedLabel = useMemo(() => {
    if (!value) return "";
    const person = personnel.find((p) => p.name === value);
    return person ? label(person) : value;
  }, [personnel, value]);

  const matches = useMemo(() => filterOptions(personnel, query, label, (p) => p.name), [personnel, query]);

  // A new search starts at the top; opening the list starts on the current choice.
  useEffect(() => {
    setHighlight(matches.length ? 0 : -1);
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  // Disabled mid-search (a payment started): drop the search so the choice shows again.
  useEffect(() => {
    if (disabled) {
      setOpen(false);
      setQuery("");
    }
  }, [disabled]);

  useEffect(() => () => {
    if (blurTimer.current) clearTimeout(blurTimer.current);
  }, []);

  // Keep the highlighted option in view by scrolling the list itself - scrollIntoView would
  // also scroll the dialog around it on a short screen.
  useEffect(() => {
    const list = listRef.current;
    if (!showing || highlight < 0 || !list) return;
    const item = list.querySelector<HTMLElement>(`[data-index="${highlight}"]`);
    if (!item) return;
    if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight;
    }
  }, [highlight, showing]);

  const openList = () => {
    if (blurTimer.current) clearTimeout(blurTimer.current);
    setQuery("");
    const current = personnel.findIndex((p) => p.name === value);
    setHighlight(current >= 0 ? current : personnel.length ? 0 : -1);
    setOpen(true);
  };

  const choose = (person: DeliveryPersonnel) => {
    onChange(person.name);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      setHighlight((current) => moveHighlight(current, matches.length, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Enter") {
      if (open && highlight >= 0 && matches[highlight]) {
        event.preventDefault();
        choose(matches[highlight]);
      }
    } else if (event.key === "Escape") {
      if (open) {
        // Close the list only; the checkout's own Escape (on document) must not fire too.
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        setQuery("");
      }
    }
  };

  const optionId = (index: number) => `${listId}-option-${index}`;

  return (
    <div className={`relative ${className}`}>
      <div className="flex items-center rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus-within:ring-2 focus-within:ring-beveren-500">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-label="Delivery personnel"
          aria-expanded={showing}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showing && highlight >= 0 && matches[highlight] ? optionId(highlight) : undefined}
          disabled={disabled}
          // While searching, the current choice stays in view as the hint.
          placeholder={selectedLabel || "Select Delivery Personnel"}
          value={showing ? query : selectedLabel}
          onFocus={openList}
          onClick={() => {
            if (!open) openList();
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          // Let a click on an option land before the list closes.
          onBlur={() => {
            blurTimer.current = setTimeout(() => setOpen(false), 150);
          }}
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

      {showing && (
        <div className="absolute bottom-full left-0 z-50 mb-1 w-full min-w-[14rem] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
          {loading || error || matches.length === 0 ? (
            <p role="status" className={`px-4 py-2 text-sm ${error ? "text-red-500 dark:text-red-400" : "text-gray-500 dark:text-gray-400"}`}>
              {loading
                ? "Loading delivery personnel..."
                : error
                  ? error
                  : personnel.length
                    ? `No one matches "${query.trim()}"`
                    : "No delivery personnel found"}
            </p>
          ) : (
            <ul id={listId} ref={listRef} role="listbox" aria-label="Delivery personnel" className="relative max-h-64 overflow-y-auto py-1">
              {matches.map((person, index) => (
                <li
                  key={person.name}
                  id={optionId(index)}
                  data-index={index}
                  role="option"
                  aria-selected={index === highlight}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => choose(person)}
                  className={`cursor-pointer px-4 py-2 text-sm text-gray-900 dark:text-white ${
                    index === highlight ? "bg-beveren-50 dark:bg-gray-700" : ""
                  } ${person.name === value ? "font-semibold" : ""}`}
                >
                  {label(person)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
