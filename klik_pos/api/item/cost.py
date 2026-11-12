"""Which cost a till shows (POS Profile 'Cost Display'), and the last purchase invoice rate."""

import frappe
from frappe.utils import flt

COST_FIELD = "custom_cost_display"
HIDDEN, VALUATION, LAST_PURCHASE = "Hidden", "Valuation", "Last Purchase Cost"


def cost_mode(profile):
	"""The profile's Cost Display; anything unknown (no field yet, blank) counts as Hidden."""
	mode = (profile or {}).get(COST_FIELD)
	return mode if mode in (VALUATION, LAST_PURCHASE) else HIDDEN


def last_purchase_rates(item_codes, company):
	"""{item_code: (rate per stock UOM in company currency excl. tax, posting_date)} from the
	newest submitted, non-return Purchase Invoice of `company` that has the item."""
	if not item_codes or not company:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT item_code, rate, posting_date FROM (
			SELECT pii.item_code,
				pii.base_net_rate / IFNULL(NULLIF(pii.conversion_factor, 0), 1) AS rate,
				pi.posting_date,
				ROW_NUMBER() OVER (
					PARTITION BY pii.item_code
					ORDER BY pi.posting_date DESC, pi.posting_time DESC, pi.creation DESC, pii.idx DESC
				) AS rn
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.company = %(company)s
				AND pii.item_code IN %(items)s
		) newest WHERE rn = 1
		""",
		{"company": company, "items": tuple(item_codes)},
		as_dict=True,
	)
	return {r.item_code: (flt(r.rate), r.posting_date) for r in rows}
