"""Hand the site back as it was after a test run.

ERPNext's test bootstrap (erpnext/tests/utils.py, BootStrapTestData) runs on every
import and commits Asia/Kolkata, Banker's Rounding, Standard Selling and its stock
defaults into the site. On a working site that sends tills to Closing Shift (the
shift looks like yesterday's). This snapshots those settings before the run and
writes them back when the process exits, pass or fail.
"""

import atexit
import time

import frappe

# What BootStrapTestData.update_*_settings() changes.
SETTINGS = {
	"System Settings": ("time_zone", "language", "currency_precision", "float_precision", "rounding_method"),
	"Selling Settings": ("selling_price_list",),
	"Support Settings": ("track_service_level_agreement",),
	"Stock Settings": (
		"item_naming_by",
		"valuation_method",
		"stock_uom",
		"auto_indent",
		"auto_insert_price_list_rate_if_missing",
		"update_price_list_based_on",
		"set_qty_in_transactions_based_on_serial_no_input",
		"enable_serial_and_batch_no_for_item",
	),
}


def snapshot():
	rows = frappe.db.sql(
		"select doctype, field, value from tabSingles where doctype in %(dts)s",
		{"dts": tuple(SETTINGS)},
		as_dict=True,
	)
	return {(r.doctype, r.field): r.value for r in rows if r.field in SETTINGS[r.doctype]}


def restore(saved, site=None):
	if site and not getattr(frappe.local, "db", None):
		frappe.init(site=site)
		frappe.connect()
	# Another session's test run on the same site can deadlock this write: retry a few times.
	for attempt in range(5):
		try:
			for (doctype, field), value in saved.items():
				frappe.db.set_single_value(doctype, field, value)
			frappe.db.commit()  # nosemgrep: the run is over, nothing to roll back into
			break
		except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
			frappe.db.rollback()
			if attempt == 4:
				raise
			time.sleep(2)
	frappe.clear_cache()


def keep_site_settings():
	"""Called from klik_pos/tests/__init__.py (imported once per run): it runs before any test module imports
	erpnext.tests.utils, so the snapshot holds the site's own values. (Frappe's before_tests
	hook comes after discovery has imported the modules, so it would snapshot the test values.)"""
	atexit.register(restore, snapshot(), frappe.local.site)
