"use client";

import { createPortal } from "react-dom";
import { formatCurrencyWithSymbol } from "../utils/currency";
import type { PriceOption } from "../utils/priceOptions";

interface PriceListPopupProps {
  options: PriceOption[];
  selectedIndex: number;
  customValue: string;
  anchorRect: { top: number; left: number; bottom: number } | null;
  currencySymbol?: string;
}

export default function PriceListPopup({
  options,
  selectedIndex,
  customValue,
  anchorRect,
  currencySymbol,
}: PriceListPopupProps) {
  if (typeof window === "undefined" || !anchorRect) return null;

  return createPortal(
    <div
      style={{
        position: "fixed",
        top: anchorRect.bottom + 6,
        left: anchorRect.left,
        zIndex: 999999,
      }}
      className="w-56 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-2xl overflow-hidden py-1"
    >
      {options.map((option, index) => {
        const isSelected = index === selectedIndex;
        return (
          <div
            key={option.label}
            className={`flex items-center justify-between px-3 py-2 text-sm ${
              isSelected
                ? "bg-beveren-50 dark:bg-beveren-900/30 text-beveren-700 dark:text-beveren-300"
                : "text-gray-700 dark:text-gray-200"
            }`}
          >
            <span className="truncate">{option.label}</span>
            {option.isCustom && isSelected ? (
              <input
                readOnly
                value={customValue}
                className="w-20 text-right bg-transparent outline-none font-semibold"
                aria-label="Custom price"
              />
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
