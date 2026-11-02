"""The till's door to cecypo_powerpack's minimum selling price = price list.

A supervisor standing at the till picks their name and enters their PIN; PowerPack checks it
(with lockout) and returns a short-lived token covering the cart's below-minimum lines as
previewed. The till sends the token with the checkout (see _apply_price_authorisation).
"""

import frappe
from frappe import _

from klik_pos.api.sales_invoice import _build_preview_doc, _powerpack_floor_installed


@frappe.whitelist()
def get_supervisors():
	if not _powerpack_floor_installed():
		return []
	from cecypo_powerpack.pos_supervisor_pin import get_pos_supervisors

	return get_pos_supervisors()


@frappe.whitelist(methods=["POST"])
def authorise(data, supervisor, pin):
	if not _powerpack_floor_installed():
		return {"ok": False, "token": None, "message": _("Minimum selling price is not set up on this site.")}
	from cecypo_powerpack.pos_supervisor_pin import authorise as authorise_rows

	doc, _los = _build_preview_doc(data)
	return authorise_rows(doc, supervisor, pin)
