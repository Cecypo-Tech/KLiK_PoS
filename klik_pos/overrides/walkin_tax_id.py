def sync_walkin_tax_id(doc, method=None):
	"""validate on Quotation, Sales Order, Sales Invoice, Delivery Note: a walk-in PIN in
	custom_walkin_tax_id becomes the document's tax_id.

	Runs after Frappe re-fetches tax_id from the Customer (Document._validate_links), so the
	walk-in's PIN wins over the Walk In customer's blank one on every draft save."""
	if not doc.meta.has_field("custom_walkin_tax_id"):
		return
	pin = (doc.custom_walkin_tax_id or "").strip().upper()
	if not pin:
		return
	doc.custom_walkin_tax_id = pin
	if doc.meta.has_field("tax_id"):
		doc.tax_id = pin
