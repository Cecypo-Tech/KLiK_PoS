"""What happens to return value that cannot go back as cash.

Named customers may keep it as credit (default) or exchange now. Walk In may not keep:
nobody can prove the credit is theirs later - exchange now, refund, or a manager
override are the ways out.
"""

from unittest.mock import patch

import frappe

from klik_pos.api import sales_invoice as si
from klik_pos.api.sales_invoice import create_partial_return
from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestCreditAction(CashOnlyReturnCase):
	"""CashOnlyReturnCase (extends MpesaFirstCase) provides _sale(total, **tendered)
	on dev's _Test records. A card-paid sale leaves its whole value as credit on the
	note - the cleanest non-cash remainder to exercise."""

	def _return_with_action(self, invoice, **kwargs):
		item = invoice.items[0]
		return create_partial_return(
			invoice_name=invoice.name,
			return_items=[{"item_code": item.item_code, "return_qty": item.qty}],
			payment_method="Cash",
			return_amount=0,
			**kwargs,
		)

	def test_keep_returns_the_note_in_the_response(self):
		result = self._return_with_action(self._sale(500, card=500))
		self.assertTrue(result.get("success"), result)
		self.assertEqual(result["credit"]["note"], result["return_invoice"])
		self.assertEqual(result["credit"]["action"], "keep")
		self.assertEqual(result["credit"]["available"], 500.0)

	def test_walkin_keep_is_refused_without_the_override(self):
		# The endpoint's contract traps throws into {"success": False, "message"}; the
		# validation runs before anything persists, so no return document exists after.
		invoice = self._sale(500, card=500)
		with patch.object(si, "_is_walkin_customer", return_value=True):
			result = self._return_with_action(invoice, credit_action="keep")
		self.assertFalse(result.get("success"), result)
		self.assertIn("Walk In credit", result.get("message") or "")
		self.assertFalse(frappe.get_all("Sales Invoice", {"return_against": invoice.name, "is_return": 1}))

	def test_walkin_keep_passes_with_the_override(self):
		invoice = self._sale(500, card=500)
		with patch.object(si, "_is_walkin_customer", return_value=True):
			result = self._return_with_action(invoice, credit_action="keep", allow_walkin_credit=1)
		self.assertEqual(result["credit"]["action"], "keep")

	def test_exchange_echoes_the_action(self):
		result = self._return_with_action(self._sale(500, card=500), credit_action="exchange")
		self.assertEqual(result["credit"]["action"], "exchange")
