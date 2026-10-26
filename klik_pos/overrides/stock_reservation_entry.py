import frappe
from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import StockReservationEntry

# Mirrors QUEUE_STATUSES in klik_pos.api.sales_invoice; spelled out here so this module
# does not import that one at controller-load time.
QUEUE_HOLD_STATUSES = ("Queued", "Processing")


def is_queued_klik_draft(voucher_type: str, voucher_no: str) -> bool:
	"""A draft Sales Invoice klik is holding stock for while it waits in the submit queue."""
	if voucher_type != "Sales Invoice" or not voucher_no:
		return False
	row = frappe.db.get_value("Sales Invoice", voucher_no, ["docstatus", "queue_status"], as_dict=True)
	return bool(row and row.docstatus == 0 and row.queue_status in QUEUE_HOLD_STATUSES)


class KlikStockReservationEntry(StockReservationEntry):
	def validate_voucher(self) -> None:
		# ERPNext 16.52 (52176ecc7f) requires the voucher to be submitted. klik reserves
		# against the draft so nothing sells the stock out from under a queued sale, and
		# releases the hold after submit (_cancel_sales_invoice_reservations).
		if is_queued_klik_draft(self.voucher_type, self.voucher_no):
			return
		super().validate_voucher()
