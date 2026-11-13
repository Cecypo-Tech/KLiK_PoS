import { useCartStore, saleTypeOf } from "../../stores/cartStore";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { quotesAllowed } from "../../utils/quotesAllowed";
import { creditSalesAllowed } from "../../utils/creditSales";
import type { SaleType } from "../../utils/saleType";
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
      onChange={setSaleType}
      disabledReasons={walkin ? { credit: "Credit sales need a named customer" } : undefined}
    />
  );
}
