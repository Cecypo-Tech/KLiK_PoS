import { useEffect, useRef, useState } from "react";

interface DescriptionDialogProps {
  isOpen: boolean;
  itemName: string;
  initialValue: string;
  onSave: (value: string) => void;
  onClose: () => void;
}

/** Catalogue descriptions are usually HTML; the cashier edits the words, not the markup. */
function toPlainText(value: string | undefined | null): string {
  if (!value) return "";
  try {
    const doc = new DOMParser().parseFromString(value, "text/html");
    return (doc.body.textContent || "").trim();
  } catch {
    return value.replace(/<[^>]*>/g, "").trim();
  }
}

export default function DescriptionDialog({
  isOpen,
  itemName,
  initialValue,
  onSave,
  onClose,
}: DescriptionDialogProps) {
  const [value, setValue] = useState(() => toPlainText(initialValue));
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setValue(toPlainText(initialValue));
    const t = setTimeout(() => textareaRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [isOpen, initialValue]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const save = () => onSave(value.trim());

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { e.stopPropagation(); onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="line-description-title"
        className="w-full max-w-md rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 pt-4">
          <h2 id="line-description-title" className="text-base font-semibold text-gray-900 dark:text-white">
            Line description
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{itemName}</p>
        </div>
        <div className="px-4 py-3">
          <textarea
            ref={textareaRef}
            rows={4}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                save();
              }
            }}
            placeholder="Shown on the invoice line"
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-beveren-500"
          />
        </div>
        <div className="flex justify-end gap-2 px-4 pb-4">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            className="px-3 py-1.5 text-sm rounded-md bg-beveren-600 text-white hover:bg-beveren-700"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
