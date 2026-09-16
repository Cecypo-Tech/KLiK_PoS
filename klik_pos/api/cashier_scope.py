"""Whether the caller is held to the invoices they rang.

One rule, read from the till the caller is working at: with its
custom_allow_viewing_other_cashiers flag off (or no till at all) a cashier sees and
collects only on their own invoices. Money owed on anyone else's is for a manager, another
till, or the desk.
"""

import frappe
from frappe import _

from klik_pos.klik_pos.utils import get_current_pos_profile


def restricted_to_own():
	from klik_pos.api.sales_invoice import _profile_allows_other_cashiers

	try:
		pos_doc = get_current_pos_profile()
	except Exception:
		return True
	return not _profile_allows_other_cashiers(pos_doc)


def own_invoice_filter():
	return {"owner": frappe.session.user} if restricted_to_own() else {}


def assert_may_collect(invoice_names):
	names = [n for n in (invoice_names or []) if n]
	if not names or not restricted_to_own():
		return
	owners = dict(frappe.get_all("Sales Invoice", filters={"name": ["in", names]}, fields=["name", "owner"], as_list=True))
	for name in names:
		if owners.get(name) != frappe.session.user:
			raise frappe.PermissionError(
				_("Invoice {0} was rung by another cashier; a manager must receive payment for it.").format(name)
			)
