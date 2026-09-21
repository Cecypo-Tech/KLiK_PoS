"use client";

import { createPortal } from "react-dom";
import { formatCurrencyWithSymbol } from "../utils/currency";
import type { PriceOption } from "../utils/priceOptions";

interface PriceListPopupProps {
  options: PriceOption[];
  selectedIndex: number;
  customValue: string;
  position: { left: number; top?: number; bottom?: number };
  currencySymbol?: string;
}

export default function PriceListPopup({
  options,
  selectedIndex,
  customValue,
  position,
  currencySymbol,
}: PriceListPopupProps) {
  if (typeof window === "undefined") return null;

  return createPortal(
    <div
      data-price-popup
      style={{
        position: "fixed",
        left: position.left,
        top: position.top,
        bottom: position.bottom,
        zIndex: 999999,
      }}
      className="w-56 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-2xl overflow-hidden py-1"
    >
      {options.map((option, index) => {
        const isSelected = index === selectedIndex;
        return (
          <div
            key={`${option.label}-${index}`}
            className={`flex items-center justify-between px-3 py-2 text-sm ${
              isSelected
                ? "bg-beveren-50 dark:bg-beveren-900/30 text-beveren-700 dark:text-beveren-300"
                : "text-gray-700 dark:text-gray-200"
            }`}
          >
            <span className="truncate">{option.label}</span>
            {option.isCustom && isSelected ? (
              <span className="flex items-center gap-1 font-semibold">
                {currencySymbol}
                <input
                  readOnly
                  value={customValue}
                  className="w-16 text-right bg-transparent outline-none"
                  aria-label="Custom price"
                />
              </span>
            ) : (
              <span className="font-semibold tabular-nums">
                {formatCurrencyWithSymbol(option.rate, currencySymbol)}
              </span>
            )}
          </div>
        );
      })}
    </div>,
    document.body
  );
}
