import { useCartStore, saleTypeOf } from "../../stores/cartStore";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { quotesAllowed } from "../../utils/quotesAllowed";
import { creditSalesAllowed } from "../../utils/creditSales";
import type { SaleType } from "../../utils/saleType";
import { toast } from "react-toastify";
import SaleTypeControl from "./SaleTypeControl";

/** The cart's Quote / Cash Sale | Credit Sale control, wired to the till and the cart. */
export default function CartSaleType() {
  const posDetails = usePOSProfileStore((s) => s.posDetails);
  const value = useCartStore(saleTypeOf);
  const setSaleType = useCartStore((s) => s.setSaleType);
  const walkin = useCartStore((s) => (s.selectedCustomer as { isWalkin?: number } | null)?.isWalkin === 1);
  const options: SaleType[] = [
    ...(quotesAllowed(posDetails) ? (["quote"] as const) : []),
    "sale",
    ...(creditSalesAllowed(posDetails) ? (["credit"] as const) : []),
  ];
  return (
    <SaleTypeControl
      value={value}
      options={options}
      onChange={(type) => {
        // Credit needs a named customer: go and pick one rather than refusing the click.
        if (type === "credit" && walkin) {
          toast.info("Credit sale needs a named customer");
          document.getElementById("pos-customer-btn")?.click();
          return;
        }
        setSaleType(type);
      }}
    />
  );
}
