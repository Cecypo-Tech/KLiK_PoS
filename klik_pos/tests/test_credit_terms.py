"""A credit sale's due date from Payment Terms at the till.

The cashier picks a Payment Terms Template instead of typing a date: the customer's own terms
(Customer, then Customer Group, then Company - ERPNext's order), else the shortest one. ERPNext
blanks the template on a POS invoice, so it only decides the due date, which the server works
out itself. No templates at all: the till keeps its date field.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, get_last_day, getdate, nowdate

from klik_pos.api import payment_terms
from klik_pos.api.payment_terms import credit_due_date, credit_terms

PREFIX = "_Klik Terms "
ONE_DAY = PREFIX + "1 Day"
FORTY_FIVE = PREFIX + "45 Days"
NEXT_MONTH = PREFIX + "End of Next Month"


def _template(name, based_on, days=0, months=0):
	if frappe.db.exists("Payment Terms Template", name):
		return name
	doc = frappe.new_doc("Payment Terms Template")
	doc.template_name = name
	doc.append(
		"terms",
		{
			"due_date_based_on": based_on,
			"credit_days": days,
			"credit_months": months,
			"invoice_portion": 100,
		},
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _customer(name, payment_terms=None, customer_group=None):
	doc = frappe.new_doc("Customer")
	doc.customer_name = name
	doc.customer_type = "Company"
	# A group without terms of its own, so only the test's own terms decide.
	doc.customer_group = customer_group or frappe.db.get_value(
		"Customer Group", {"is_group": 0, "payment_terms": ["is", "not set"]}, "name"
	)
	doc.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	doc.payment_terms = payment_terms
	doc.insert(ignore_permissions=True)
	return doc.name


class CreditTermsCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		_template(ONE_DAY, "Day(s) after invoice date", days=1)
		_template(FORTY_FIVE, "Day(s) after invoice date", days=45)
		_template(NEXT_MONTH, "Month(s) after the end of the invoice month", months=1)

	def setUp(self):
		# The till's company decides the Company-level default; none here unless a test says so.
		self.company = patch.object(payment_terms, "_till_company", return_value=None)
		self.company.start()
		self.addCleanup(self.company.stop)

	def _names(self, result):
		return [t["name"] for t in result["templates"]]


class TestTheList(CreditTermsCase):
	def test_every_template_with_the_date_it_gives_earliest_first(self):
		result = credit_terms()
		today = getdate(nowdate())
		given = {t["name"]: t["due_date"] for t in result["templates"]}
		self.assertEqual(given[ONE_DAY], str(add_days(today, 1)))
		self.assertEqual(given[FORTY_FIVE], str(add_days(today, 45)))
		self.assertEqual(given[NEXT_MONTH], str(get_last_day(add_months(today, 1))))
		dates = [t["due_date"] for t in result["templates"]]
		self.assertEqual(dates, sorted(dates))

	def test_no_templates_means_the_date_field(self):
		with patch.object(payment_terms, "_template_names", return_value=[]):
			self.assertEqual(credit_terms(), {"templates": [], "default": None})


class TestTheDefault(CreditTermsCase):
	def test_the_customer_s_own_terms(self):
		customer = _customer(PREFIX + "Own Terms Co", payment_terms=FORTY_FIVE)
		self.assertEqual(credit_terms(customer)["default"], FORTY_FIVE)

	def test_the_customer_group_s_terms_when_the_customer_has_none(self):
		group = frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": PREFIX + "Group",
				"parent_customer_group": frappe.db.get_value("Customer Group", {"is_group": 1}, "name"),
				"payment_terms": NEXT_MONTH,
			}
		).insert(ignore_permissions=True)
		customer = _customer(PREFIX + "Group Terms Co", customer_group=group.name)
		self.assertEqual(credit_terms(customer)["default"], NEXT_MONTH)

	def test_the_company_s_terms_when_neither_has_any(self):
		customer = _customer(PREFIX + "Company Terms Co")
		self.company.stop()
		with (
			patch.object(payment_terms, "_till_company", return_value="_Test Company"),
			patch("frappe.get_cached_value", side_effect=_company_terms),
		):
			self.assertEqual(credit_terms(customer)["default"], FORTY_FIVE)
		self.company.start()

	def test_the_earliest_when_no_terms_apply(self):
		customer = _customer(PREFIX + "No Terms Co")
		result = credit_terms(customer)
		self.assertEqual(result["default"], result["templates"][0]["name"])

	def test_no_customer_gets_the_earliest(self):
		result = credit_terms()
		self.assertEqual(result["default"], result["templates"][0]["name"])


_real_cached_value = frappe.get_cached_value


def _company_terms(doctype, name, *args, **kwargs):
	if doctype == "Company" and kwargs.get("fieldname") == "payment_terms":
		return FORTY_FIVE
	return _real_cached_value(doctype, name, *args, **kwargs)


class TestTheDueDate(CreditTermsCase):
	def test_a_template_s_due_date(self):
		self.assertEqual(credit_due_date(FORTY_FIVE, "2026-10-02"), "2026-11-16")
		self.assertEqual(credit_due_date(NEXT_MONTH, "2026-10-02"), "2026-11-30")

	def test_an_unknown_template_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			credit_due_date(PREFIX + "Nope")


class TestCheckout(CreditTermsCase):
	"""parse_invoice_data works the due date out from the template; the posted date is display."""

	def _parse(self, **extra):
		from klik_pos.api.sales_invoice import parse_invoice_data

		data = {
			"customer": {"id": "_Test Customer"},
			"items": [{"id": "_Test Item", "quantity": 1, "price": 100}],
			"paymentMethods": [],
			"isCreditSale": True,
			**extra,
		}
		profile = frappe._dict(name="Till X", custom_allow_credit_sales_as_pos=1, default_sales_type="Cash")
		with (
			patch("klik_pos.api.sales_invoice.get_current_pos_profile", return_value=profile),
			patch("klik_pos.api.sales_invoice._get_default_payment_mode", return_value=None),
		):
			return parse_invoice_data(data)

	def test_the_template_decides_the_due_date(self):
		due_date = self._parse(paymentTermsTemplate=FORTY_FIVE, dueDate="2099-01-01")[11]
		self.assertEqual(due_date, str(add_days(getdate(nowdate()), 45)))

	def test_an_unknown_template_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._parse(paymentTermsTemplate=PREFIX + "Nope", dueDate="2099-01-01")

	def test_without_a_template_the_posted_date_stands(self):
		self.assertEqual(self._parse(dueDate="2099-01-01")[11], "2099-01-01")

	def test_a_cash_sale_ignores_a_template(self):
		parsed = self._parse(
			isCreditSale=False,
			paymentTermsTemplate=FORTY_FIVE,
			paymentMethods=[{"method": "Cash", "amount": 100}],
			amountPaid=100,
		)
		self.assertIsNone(parsed[11])
