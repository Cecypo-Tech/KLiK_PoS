import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { getHeldOrders } from "../services/salesOrder";
import { addHeldOrderToCart } from "../utils/heldOrderToCart";
import { APPROVAL_REQUESTED_EVENT, approvalAnswers, type HeldRow } from "../utils/approvalWatch";

const POLL_MS = 15_000;

/**
 * Tell the cashier when a manager answers a price approval they asked for.
 *
 * The till has no realtime client, so this polls - but only while one of the cashier's own
 * held orders is pending, and checks at once when they ask. Mounted at the app root: the
 * answer may come while the cashier is mid-way through the next sale.
 */
export function useApprovalWatch() {
  const navigate = useNavigate();
  useEffect(() => {
    const me = (window as { klik_user?: string }).klik_user;
    if (!me || me === "Guest") return;
    let pending = new Set<string>();
    let busy = false;

    const resume = (name: string) => {
      toast.dismiss(`approved-${name}`);
      addHeldOrderToCart(name)
        .then((ok) => ok && navigate("/pos"))
        .catch((e: Error) => toast.error(e.message || "Could not load the order"));
    };

    const check = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await getHeldOrders({ limit: 100 });
        if (!result?.success) return;
        const answers = approvalAnswers(pending, result.data as HeldRow[], me);
        pending = answers.pending;
        for (const row of answers.approved) {
          toast.success(`${row.name} approved for ${row.customer_name || "the customer"}. Tap to resume the sale.`, {
            toastId: `approved-${row.name}`,
            autoClose: false,
            onClick: () => resume(row.name),
          });
        }
        for (const row of answers.declined) {
          toast.warning(`The manager declined the price on ${row.name}. It is back in Held.`, {
            toastId: `declined-${row.name}`,
            autoClose: false,
          });
        }
      } catch {
        // Offline or signed out: try again on the next tick.
      } finally {
        busy = false;
      }
    };

    void check();
    const timer = window.setInterval(() => { if (pending.size) void check(); }, POLL_MS);
    const onAsked = () => void check();
    window.addEventListener(APPROVAL_REQUESTED_EVENT, onAsked);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(APPROVAL_REQUESTED_EVENT, onAsked);
    };
  }, [navigate]);
}
