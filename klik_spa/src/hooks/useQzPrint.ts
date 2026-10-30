import { useState } from "react";
import { toast } from "react-toastify";
import { qzNextStep, qzPrintOptions, qzReprint, type QzRuleOption } from "../utils/qzPrint";
import { useQzPrintCount } from "./useQzPrintCount";

/**
 * Everything a QZ button needs, so every QZ button in klik_pos behaves the same
 * as the desk sidebar's: one printable rule prints at once, several open the
 * picker. Render <QzRulePicker {...picker} /> beside the button.
 *
 * `reprintBlocked`: the POS Profile's Prevent Invoice Reprinting applies and
 * this invoice has already been printed. `doctype`: a held order is a Sales Order.
 */
export function useQzPrint(
  invoiceName: string,
  enabled: boolean,
  reprintBlocked: boolean,
  doctype: string = "Sales Invoice",
) {
  const { count, recountSoon } = useQzPrintCount(invoiceName, enabled, doctype);
  // True from the click until the print is queued or the picker is cancelled,
  // so a second tap can't queue a duplicate forced reprint.
  const [busy, setBusy] = useState(false);
  const [choices, setChoices] = useState<QzRuleOption[] | null>(null);

  const send = async (rules: string[]) => {
    try {
      await qzReprint(invoiceName, doctype, rules);
      recountSoon();
    } catch {
      // qzReprint has already shown the error.
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (busy) return;
    if (reprintBlocked) {
      toast.error("Reprinting is not allowed for this invoice");
      return;
    }
    setBusy(true);
    let options: QzRuleOption[];
    try {
      options = await qzPrintOptions(invoiceName, doctype);
    } catch {
      setBusy(false);
      return;
    }
    const step = qzNextStep(options);
    if (step.kind === "none") {
      toast.warn("No print rule matches this document");
      setBusy(false);
    } else if (step.kind === "limit") {
      toast.warn("Print limit reached");
      setBusy(false);
    } else if (step.kind === "print") {
      await send(step.rules);
    } else {
      setChoices(step.options);
    }
  };

  const picker = {
    open: choices !== null,
    options: choices ?? [],
    onConfirm: (rules: string[]) => {
      setChoices(null);
      void send(rules);
    },
    onCancel: () => {
      setChoices(null);
      setBusy(false);
    },
  };

  return { count, busy, start: () => void start(), picker };
}
