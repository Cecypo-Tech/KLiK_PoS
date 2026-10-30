import { useQzPrint } from "../hooks/useQzPrint";
import QzPrintIcon from "./QzPrintIcon";
import QzRulePicker from "./QzRulePicker";

/**
 * The QZ button on a held order's row: a held order is a draft Sales Order, so it
 * prints through the site's Sales Order routing rules. A component of its own
 * because each row needs its own useQzPrint.
 */
export default function HeldOrderQzButton({ orderId, className, iconSize }: {
  orderId: string;
  className: string;
  iconSize: number;
}) {
  // `enabled` only drives the print count: off, or the Held tab fetches a count per row.
  const qz = useQzPrint(orderId, false, false, "Sales Order");
  return (
    <>
      <button type="button" title="QZ Print" aria-label="QZ Print" className={`${className} flex items-center`}
        onClick={qz.start} disabled={qz.busy}>
        <QzPrintIcon size={iconSize} />
      </button>
      <QzRulePicker {...qz.picker} />
    </>
  );
}
