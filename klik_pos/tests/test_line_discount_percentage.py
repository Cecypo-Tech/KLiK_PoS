"""A line discount given in % is saved as that %, as ERPNext's own form saves it.

The till sends the discounted rate, and ERPNext stored the gap only as discount_amount with
discount_percentage 0 (POS-08473), so reports by discount % saw none.
"""

from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api import sales_invoice as si
from klik_pos.tests.pos_fixtures import open_own_shift
from klik_pos.tests.test_customer_credit_checkout import CUSTOMER, ITEM, _ensure_customer, _ensure_service_item

TILL = "TEST-LINE-DISCOUNT-PCT-TILL"


class TestLineDiscountPercentage(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ready = bool(open_own_shift(cls, TILL))

	def setUp(self):
		if not self.ready:
			self.skipTest("no till to copy on this site")
		_ensure_customer()
		_ensure_service_item()

	def _line(self, price, pct):
		item = {"id": ITEM, "quantity": 1, "price": price, "price_list_rate": 100, "uom": "Nos",
			"discountPercentage": pct, "discountAmount": 100 - price}
		doc = si.build_sales_invoice_doc(CUSTOMER, [item], 0, None, None, "B2C", include_payments=False)
		doc.run_method("calculate_taxes_and_totals")
		return doc.items[0]

	def test_a_percent_discount_is_kept_as_its_percent(self):
		row = self._line(90, 10)
		self.assertEqual((flt(row.discount_percentage), flt(row.rate)), (10, 90))

	def test_a_rate_that_is_not_the_list_less_the_percent_keeps_an_amount(self):
		row = self._line(85, 10)
		self.assertEqual((flt(row.discount_percentage), flt(row.rate)), (0, 85))
