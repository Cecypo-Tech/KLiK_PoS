"""A receipt recorded twice can lose its spare copy.

klik refuses to cancel a register row while the sale it names is live, because
cancelling the row used to cancel the Payment Entry under that sale. A spare copy of
a receipt - no Payment Entry, its twin still naming the same sale - carries nothing
the sale depends on.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.overrides import mpesa_register

REGISTER = "Mpesa C2B Payment Register"
INVOICE = "CS-GUARD-TEST"


def _row(name, transid, **fields):
	doc = frappe.get_doc(
		{
			"doctype": REGISTER,
			"name": name,
			"transid": transid,
			"transamount": 100,
			"businessshortcode": "GUARDTEST",
			"docstatus": 1,
			"sales_invoice": INVOICE,
			**fields,
		}
	)
	doc.db_insert()
	return frappe.get_doc(REGISTER, name)


class TestCancelGuard(FrappeTestCase):
	def _live_invoice(self):
		real = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			if doctype == "Sales Invoice" and args and args[0] == INVOICE:
				return 1
			return real(doctype, *args, **kwargs)

		return patch.object(mpesa_register.frappe.db, "get_value", side_effect=get_value)

	def test_twin_without_entry_cancels(self):
		transid = f"GT{frappe.generate_hash(length=6).upper()}"
		_row(f"{transid}-A", transid)
		spare = _row(f"{transid}-B", transid)
		with self._live_invoice():
			mpesa_register.refuse_cancel_while_invoice_live(spare)  # no refusal

	def test_sole_row_still_guarded(self):
		transid = f"GT{frappe.generate_hash(length=6).upper()}"
		only = _row(f"{transid}-A", transid)
		with self._live_invoice(), self.assertRaisesRegex(frappe.ValidationError, "Cancel Sales Invoice"):
			mpesa_register.refuse_cancel_while_invoice_live(only)

	def test_twin_with_an_entry_still_guarded(self):
		transid = f"GT{frappe.generate_hash(length=6).upper()}"
		_row(f"{transid}-A", transid)
		spare = _row(f"{transid}-B", transid)
		spare.payment_entry = "ACC-PAY-GUARD"
		with (
			self._live_invoice(),
			patch.object(mpesa_register.frappe.db, "sql_list", return_value=[]),
			self.assertRaisesRegex(frappe.ValidationError, "Cancel Sales Invoice"),
		):
			mpesa_register.refuse_cancel_while_invoice_live(spare)
