"""Fixtures that pin what the checkout tests depend on.

Three separate ambient-config breakages traced back to this file not existing.
"""

import contextlib

import frappe


def pick_payment_mode(profile_name):
	"""A deterministic mode of payment for a POS Profile.

	`frappe.db.get_value("POS Payment Method", {"parent": ...}, "mode_of_payment")` is
	UNORDERED. With one payment method on the profile it looks stable; add a few and it
	silently starts returning a different mode. Prefer the profile's default, then the
	lowest idx. Never reintroduce the unordered get_value.
	"""
	rows = frappe.get_all(
		"POS Payment Method",
		filters={"parent": profile_name, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "`default`", "idx"],
		order_by="idx asc",
	)
	if not rows:
		return None
	for row in rows:
		if row.get("default"):
			return row["mode_of_payment"]
	return rows[0]["mode_of_payment"]


def payable_total(customer, items, mode_of_payment):
	"""What the checkout will actually demand for `items` - not the sum of line prices.

	A company-wide default Sales Taxes and Charges Template (`Kenya Tax - DC` on this
	bench) adds tax the payload never mentions, so paying the line price produces a
	PARTIALLY PAID invoice. That passes while the POS Profile allows partial payment and
	fails the moment it does not. Ask the builder rather than assuming a tax rate, so the
	tests hold whether or not a default template exists.
	"""
	from klik_pos.api.sales_invoice import build_sales_invoice_doc

	doc = build_sales_invoice_doc(customer, items, 0, None, mode_of_payment, "B2C", include_payments=False)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	return doc.rounded_total or doc.grand_total


@contextlib.contextmanager
def pos_profile_settings(profile_name, **values):
	"""Pin POS Profile fields for the block, restoring them afterwards - even on failure.

	It has to be a DB write: ERPNext reads the profile from the invoice's link during
	validation (`set_pos_fields`, the partial-payment check), so patching a cached profile
	object never reaches it. Two fields have bitten so far:

	- allow_partial_payment: gates any underpaid sale.
	- taxes_and_charges: `set_pos_fields` copies it onto every POS invoice, blanking a
	  company-default template while leaving its tax rows behind. erpnext_express then
	  rejects "tax rows without a template" for any user with an Express role - so a
	  cashier cannot sell at all on a profile with no template, while Administrator can.
	"""
	original = frappe.db.get_value("POS Profile", profile_name, list(values), as_dict=True)
	for field, value in values.items():
		frappe.db.set_value("POS Profile", profile_name, field, value)
	frappe.db.commit()
	try:
		yield
	finally:
		for field in values:
			frappe.db.set_value("POS Profile", profile_name, field, original[field])
		frappe.db.commit()


def default_sales_tax_template(company):
	"""The company's default Sales Taxes and Charges Template, or None."""
	return frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": company, "is_default": 1}, "name"
	)


def company_with_warehouses(count=2):
	"""A company with at least `count` leaf warehouses, the same one every run.

	`frappe.db.get_value("Company", {}, "name")` is whichever company the table returns first:
	on this bench a test-created company with no warehouse at all, so every fixture built on
	its warehouse (a Bin, a till) failed with "warehouse is mandatory".
	"""
	rows = frappe.db.sql(
		"""SELECT company FROM `tabWarehouse`
		WHERE is_group = 0 AND disabled = 0 AND IFNULL(company, '') != ''
		GROUP BY company HAVING COUNT(*) >= %s ORDER BY company LIMIT 1""",
		count,
	)
	return rows[0][0] if rows else None


def open_own_shift(test_class, till, prefer=None, user="Administrator"):
	"""Give a test class a shift of its own, opened today on a till of its own.

	The checkout tests used to borrow whatever shift `user` had open on the site. ERPNext
	refuses a sale on a shift opened on an earlier day ("POS Opening Entry ... is outdated"),
	so one shift left open overnight failed every checkout test, and with no shift open they
	all skipped. This copies a real till (the first one `prefer` accepts) to `till`, opens a
	shift on it for `user`, makes it the shift klik treats as current, and registers a class
	cleanup that removes both and restores the user's previous current shift.

	Returns the copied POS Profile, or None when the site has no till to copy.
	"""
	from klik_pos.api.shift import JOINED_SHIFT_KEY

	sources = [p for p in frappe.get_all("POS Profile", {"disabled": 0}, pluck="name", order_by="creation") if p != till]
	source = next((p for p in sources if prefer is None or prefer(p)), None)
	mode = source and pick_payment_mode(source)
	if not mode:
		return None
	_drop_till(till)  # a run that died half-way

	profile = frappe.copy_doc(frappe.get_doc("POS Profile", source))
	profile.set("applicable_for_users", [{"user": user}])
	profile.insert(ignore_permissions=True, set_name=till)

	entry = frappe.new_doc("POS Opening Entry")
	entry.update(
		{
			"period_start_date": frappe.utils.now(),
			"posting_date": frappe.utils.nowdate(),
			"company": profile.company,
			"pos_profile": profile.name,
			"user": user,
		}
	)
	row = {"mode_of_payment": mode, "opening_amount": 0}
	if frappe.get_meta("POS Opening Entry Detail").has_field("custom_variance_reason"):
		# The till asks why an opening differs from the last closing on this profile.
		row["custom_variance_reason"] = "test fixture: shift opened with an empty drawer"
	entry.append("balance_details", row)
	# Read before the submit: klik's on_submit (remember_opened_shift) makes the new shift the
	# user's current one. From the table, not get_user_default, which reads a per-process cache.
	previous = frappe.db.get_value("DefaultValue", {"parent": user, "defkey": JOINED_SHIFT_KEY}, "defvalue")
	entry.insert(ignore_permissions=True)
	entry.submit()

	frappe.db.commit()

	def cleanup():
		frappe.set_user("Administrator")
		_drop_till(till)
		if previous and frappe.db.exists("POS Opening Entry", previous):
			frappe.defaults.set_user_default(JOINED_SHIFT_KEY, previous, user)
		else:
			frappe.defaults.clear_user_default(JOINED_SHIFT_KEY, user)
		frappe.db.commit()

	test_class.addClassCleanup(cleanup)
	return profile


def _drop_till(till):
	"""Remove a test till and every shift opened on it (submitted shifts included)."""
	from klik_pos.api.shift import JOINED_SHIFT_KEY

	for name in frappe.get_all("POS Opening Entry", filters={"pos_profile": till}, pluck="name"):
		# Shift names are reused once deleted, so nobody may stay pointed at this one.
		frappe.defaults.clear_default(JOINED_SHIFT_KEY, value=name)
		frappe.db.sql("update `tabPOS Opening Entry` set docstatus = 2 where name = %s", (name,))
		frappe.clear_document_cache("POS Opening Entry", name)
		frappe.delete_doc("POS Opening Entry", name, force=True, ignore_permissions=True, ignore_on_trash=True)
	if frappe.db.exists("POS Profile", till):
		frappe.delete_doc("POS Profile", till, force=True, ignore_permissions=True)
