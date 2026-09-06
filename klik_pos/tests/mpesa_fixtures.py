"""Fixtures for the `Mpesa C2B Payment Register` (doctype owned by frappe_mpsa_payments).

Serves both automated tests and manual QA. A row is "pending" at docstatus 0, and the POS
only lists rows whose `businessshortcode` is configured in `Mpesa Settings` for the company -
which is why the dev register can look full and still show nothing.
"""

import frappe

QA_LABEL_PREFIX = "QA"


def make_c2b_payment(company, shortcode, amount, msisdn, billrefnumber=None, names=None):
	"""Insert one pending C2B register row.

	`full_name` is derived in before_insert -> set_missing_values() from firstname/lastname
	and cannot be set directly. That same hook hardcodes currency="KES", so on a company
	whose currency is not KES the row is patched afterwards: create_payment_entry() throws
	on a party/transaction currency mismatch.
	"""
	first, last = names or ("Zawadi", "Mwangi")
	doc = frappe.get_doc(
		{
			"doctype": "Mpesa C2B Payment Register",
			"businessshortcode": str(shortcode),
			"transactiontype": "Pay Bill",
			"transid": f"TX{frappe.generate_hash(length=8).upper()}",
			"transtime": "120000",
			"transamount": amount,
			"billrefnumber": billrefnumber or f"BILL{frappe.generate_hash(length=6).upper()}",
			"msisdn": str(msisdn),
			"firstname": first,
			"lastname": last,
			"posting_date": frappe.utils.nowdate(),
			"posting_time": frappe.utils.nowtime(),
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)

	currency = frappe.db.get_value("Company", company, "default_currency")
	if currency and currency != "KES":
		frappe.db.set_value("Mpesa C2B Payment Register", doc.name, "currency", currency)
		doc.reload()
	return doc


def _shortcode_for(company):
	from klik_pos.api.mpesa import _mpesa_shortcodes_for_company

	shortcodes = _mpesa_shortcodes_for_company(company)
	if not shortcodes:
		frappe.throw(f"No Mpesa Settings business shortcode configured for {company}")
	return shortcodes


def seed_qa_batch(company="Dev Co", label=None):
	"""Seed the register with rows covering the manual M-Pesa QA scenarios.

	Every row carries `label` in its billrefnumber so the POS search (which needs 3+
	characters) finds exactly this batch, and `cleanup_qa_batch` can remove exactly it.
	"""
	label = label or f"{QA_LABEL_PREFIX}{frappe.utils.nowdate().replace('-', '')[2:]}"
	shortcode = _shortcode_for(company)[0]

	# amount, msisdn, scenario - each row a distinct phone so per-transaction
	# phone numbers are visibly different on the invoice and the receipt.
	scenarios = [
		(100, "254700000101", "split-1 of 3"),
		(200, "254700000102", "split-2 of 3"),
		(300, "254700000103", "split-3 of 3"),
		(250, "254700000201", "straddle-A"),
		(450, "254700000202", "straddle-B"),
		(5000, "254700000301", "overpay"),
		(50, "254700000401", "spare-small"),
		(1000, "254700000402", "spare-large"),
	]

	created = []
	for amount, msisdn, scenario in scenarios:
		doc = make_c2b_payment(
			company=company,
			shortcode=shortcode,
			amount=amount,
			msisdn=msisdn,
			billrefnumber=f"{label}-{scenario}",
			names=("QA", scenario.replace("-", " ").title()),
		)
		created.append(
			{"name": doc.name, "amount": amount, "msisdn": msisdn, "scenario": scenario}
		)
	frappe.db.commit()

	print(f"Seeded {len(created)} pending rows on shortcode {shortcode} for {company}.")
	print(f"Search the POS M-Pesa panel for: {label}")
	for row in created:
		print(f"  {row['name']:<22} {row['amount']:>8}  {row['msisdn']}  {row['scenario']}")
	print("\nSuggested QA sales:")
	print("  600 sale  -> pick split-1 + split-2 + split-3 (three payment rows, three phones)")
	print("  500 sale  -> pick straddle-A + straddle-B (second receipt partially consumed)")
	print("  200 sale  -> pick overpay (embedded row plus unallocated spillover)")
	return created


def cleanup_qa_batch(label):
	"""Delete the still-pending rows of one seeded batch. Consumed rows are left alone."""
	names = frappe.get_all(
		"Mpesa C2B Payment Register",
		filters={"docstatus": 0, "billrefnumber": ["like", f"{label}-%"]},
		pluck="name",
	)
	for name in names:
		frappe.delete_doc("Mpesa C2B Payment Register", name, force=True, ignore_permissions=True)
	frappe.db.commit()
	print(f"Deleted {len(names)} pending rows for label {label}.")
	return len(names)
