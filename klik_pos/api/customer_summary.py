"""One customer's account position, for the stat cards on the customer detail page.

Deliberately NOT sourced from klik_pos.api.sales_invoice.get_sales_invoices: that endpoint is
POS till history (it filters on custom_pos_opening_entry) and matches customers with a LIKE
substring. Cards built on it under-report a customer who also has back-office invoices, which
is most of them.
"""

import frappe
from frappe import _
from frappe.utils import flt

from klik_pos.api.cashier_scope import own_invoice_filter, restricted_to_own
from klik_pos.api.receivables import get_customer_receivables
from klik_pos.klik_pos.utils import get_current_pos_profile


def _default_company():
	"""Resolve the company for the currency figure, POS profile first.

	Falls back to the user's default company when no POS profile resolves for the current
	session (e.g. no POS Opening Entry and no POS Profile User row) — get_current_pos_profile
	throws in that case rather than returning None.
	"""
	try:
		pos_profile = get_current_pos_profile()
		if pos_profile and pos_profile.company:
			return pos_profile.company
	except Exception:
		pass

	return frappe.defaults.get_user_default("Company")


def _outstanding_for(customer):
	"""Delegate to the AR path so this always agrees with the Statement and the By Customer tab.

	Returns None, not 0.0, when the figure could not be determined — get_customer_receivables
	never raises (it catches internally and returns {"success": False, "error": ...}, with no
	"data" key at all), and a permission failure or a broken AR report must not be reported as
	a confident "customer owes nothing". 0.0 is reserved for the case the AR path actually
	resolved and genuinely found no outstanding balance and no unallocated advance — its "data"
	list is empty then, and that emptiness is itself the answer, never assume a row exists.
	"""
	response = get_customer_receivables(customer=customer) or {}
	if not response.get("success"):
		return None
	data = response.get("data") or []
	if not data:
		return 0.0
	return flt(data[0].get("outstanding") or 0.0, 2)


@frappe.whitelist()
def get_customer_account_summary(customer):
	"""Return the four figures the customer detail page shows as headline cards.

	All four come from one call so they cannot disagree with each other, and none of them
	depend on whatever filter the user has applied to the invoice table below.

	`outstanding` is `float | None`: None means the AR path could not determine it (a
	permission failure or a broken report), not that the customer owes nothing — the caller
	should render that as unknown, not as zero. `currency` is `str | None` for the same
	reason: no company resolved for the session.
	"""
	if not customer:
		frappe.throw(_("Customer is required."))

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} not found.").format(customer))

	restricted = restricted_to_own()

	# get_all applies read permissions; an exact customer filter, never a LIKE.
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, **own_invoice_filter()},
		fields=["base_grand_total", "is_return"] + (["outstanding_amount"] if restricted else []),
	)

	# A return is not an order: it must not inflate the count or drag the average, but its
	# negative total must still reduce revenue. grand_total on a return is already negative,
	# so summing every submitted invoice already nets it in — it must not be subtracted again.
	invoice_count = sum(1 for row in rows if not row.is_return)
	net_revenue = flt(sum(flt(row.base_grand_total) for row in rows), 2)
	avg_order_value = flt(net_revenue / invoice_count, 2) if invoice_count else 0.0

	company = _default_company()

	if restricted:
		# Held to their own invoices: compute outstanding from these same filtered rows
		# rather than _outstanding_for, which would count the whole customer.
		outstanding = flt(sum(flt(row.outstanding_amount) for row in rows if not row.is_return), 2)
	else:
		outstanding = _outstanding_for(customer)

	return {
		"invoice_count": invoice_count,
		"net_revenue": net_revenue,
		"avg_order_value": avg_order_value,
		"outstanding": outstanding,
		"currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
	}


def total_spent_sql(customer_expr, alias="si"):
	"""SQL fragment for a customer's net revenue.

	base_grand_total (company currency, never grand_total, which is transaction currency
	and mixes units for a customer invoiced in more than one currency), summed over every
	submitted, non-cancelled invoice regardless of channel (POS or back-office) — the same
	AR-wide scope as get_customer_account_summary above, never narrowed to
	custom_pos_opening_entry, which under-reports any customer who also has back-office
	invoices. A return's base_grand_total is already negative, so summing it in nets it
	without a separate subtraction.

	This is the one place every "total spent" figure in the app must read from so they
	cannot disagree; customer_expr is the caller's reference to the customer (a bound
	`%s` placeholder for a standalone query, or a correlated column like `c.name` inside
	a per-row subquery).
	"""
	return f"""
		SELECT COALESCE(SUM({alias}.base_grand_total), 0)
		FROM `tabSales Invoice` {alias}
		WHERE {alias}.customer = {customer_expr}
		AND {alias}.docstatus = 1
		AND {alias}.status != 'Cancelled'
	"""


def total_orders_sql(customer_expr, alias="si"):
	"""SQL fragment counting a customer's orders: submitted, non-cancelled, not a return.

	Same AR-wide scope as total_spent_sql — see its docstring.
	"""
	return f"""
		SELECT COUNT(*)
		FROM `tabSales Invoice` {alias}
		WHERE {alias}.customer = {customer_expr}
		AND {alias}.docstatus = 1
		AND {alias}.is_return = 0
		AND {alias}.status != 'Cancelled'
	"""


def last_visit_sql(customer_expr, alias="si"):
	"""SQL fragment for a customer's most recent order date.

	Same AR-wide scope as total_spent_sql — see its docstring.
	"""
	return f"""
		SELECT MAX({alias}.posting_date)
		FROM `tabSales Invoice` {alias}
		WHERE {alias}.customer = {customer_expr}
		AND {alias}.docstatus = 1
		AND {alias}.is_return = 0
		AND {alias}.status != 'Cancelled'
	"""
