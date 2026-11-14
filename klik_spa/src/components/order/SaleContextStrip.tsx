import { Tag, Warehouse } from "lucide-react";
import { useCartStore, saleTypeOf } from "../../stores/cartStore";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import type { Customer } from "../../types/customer";
import { CustomerIcon } from "./customerMarks";
import { customerBadge } from "../../utils/customerRow";
import { SALE_TYPE_COLOUR, SALE_TYPE_LABEL } from "../../utils/saleType";

const BOX = "h-9 flex items-center gap-2 px-3 rounded-lg border border-gray-200 dark:border-gray-700 text-sm min-w-0";

/** The main top bar's sale type, customer, warehouse and price list, read-only: what checkout
 * shows in place of the editable controls while an M-Pesa payment, a submit or a hold locks the sale. */
export default function SaleContextStrip() {
  const saleType = useCartStore(saleTypeOf);
  const customer = useCartStore((s) => s.selectedCustomer) as Customer | null;
  const pickedList = useCartStore((s) => s.selectedPriceList);
  const pickedWarehouse = usePOSProfileStore((s) => s.warehouse);
  const posDetails = usePOSProfileStore((s) => s.posDetails) as { warehouse?: string; selling_price_list?: string } | null;
  const warehouse = pickedWarehouse || posDetails?.warehouse || "";
  const priceList = String(pickedList || customer?.sellingPriceList || posDetails?.selling_price_list || "");
  const badge = customer ? customerBadge(customer) : null;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <span className={`h-9 shrink-0 inline-flex items-center rounded-lg px-3 text-sm font-semibold text-white ${SALE_TYPE_COLOUR[saleType]}`}>
        {SALE_TYPE_LABEL[saleType]}
      </span>
      <div className={`${BOX} flex-[3] max-w-md min-w-[10rem] bg-white dark:bg-gray-900`} title={customer?.name}>
        {customer && <CustomerIcon customer={customer} size={16} />}
        <span className="truncate font-medium text-gray-900 dark:text-white">{customer?.name || "No customer"}</span>
        {badge && <span className={`hidden xl:inline shrink-0 text-[11px] leading-none px-1.5 py-0.5 rounded ${badge.color}`}>{badge.label}</span>}
      </div>
      {warehouse && (
        <div className={`${BOX} flex-[1] max-w-[14rem] bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300`} title={`Warehouse: ${warehouse}`}>
          <Warehouse className="w-4 h-4 shrink-0 text-gray-400" aria-hidden />
          <span className="truncate">{warehouse}</span>
        </div>
      )}
      {priceList && (
        <div className={`${BOX} flex-[1] max-w-[14rem] bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300`} title={`Price list: ${priceList}`}>
          <Tag className="w-4 h-4 shrink-0 text-gray-400" aria-hidden />
          <span className="truncate">{priceList}</span>
        </div>
      )}
    </div>
  );
}
