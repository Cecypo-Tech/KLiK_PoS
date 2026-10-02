"""Payment terms for a credit sale at the till.

The cashier picks a Payment Terms Template instead of typing a due date. ERPNext blanks the
template on a POS invoice (`set_payment_schedule`), and a till's credit sale is a POS invoice,
so the template only decides the due date: the server works it out from the template, and the
invoice keeps the date.
"""

import frappe
from erpnext.accounts.party import get_due_date_from_template, get_payment_terms_template
from frappe import _
from frappe.utils import getdate, nowdate


def _template_names():
	return frappe.get_all("Payment Terms Template", pluck="name", order_by="name")


def _till_company():
	from klik_pos.klik_pos.utils import get_current_pos_profile_lite

	queued = len(frappe.local.message_log)
	try:
		return get_current_pos_profile_lite(["company"]).get("company")
	except frappe.ValidationError:
		# No till for this user, so no Company-level terms; drop the message the lookup queued.
		del frappe.local.message_log[queued:]
		return None


def credit_due_date(template, posting_date=None):
	"""The due date `template` gives a sale posted on `posting_date` (today by default)."""
	if not template or not frappe.db.exists("Payment Terms Template", template):
		frappe.throw(_("Payment Terms Template {0} does not exist").format(frappe.bold(template)))
	posting_date = getdate(posting_date or nowdate())
	due_date = getdate(get_due_date_from_template(template, posting_date, None))
	return str(max(due_date, posting_date))


@frappe.whitelist()
def credit_terms(customer=None):
	"""Every template with the due date it gives today, earliest first, and the one to preselect:
	the customer's own terms (Customer, then Customer Group, then the till's Company - ERPNext's
	order), else the earliest. No templates: an empty list, and the till keeps its date field."""
	frappe.has_permission("Sales Invoice", "create", throw=True)
	today = nowdate()
	templates = sorted(
		({"name": name, "due_date": credit_due_date(name, today)} for name in _template_names()),
		key=lambda t: (t["due_date"], t["name"]),
	)
	if not templates:
		return {"templates": [], "default": None}

	default = None
	if customer and frappe.db.exists("Customer", customer):
		default = get_payment_terms_template(customer, "Customer", _till_company())
	if default not in {t["name"] for t in templates}:
		default = templates[0]["name"]
	return {"templates": templates, "default": default}
