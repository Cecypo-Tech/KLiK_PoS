"""Two tills submit sales on one M-Pesa receipt at the same moment.

Real threads, real connections: so fixtures are committed here and purged by hand in
tearDown - unlike every other module in this suite, nothing is rolled back for us.

A barrier holds both tills just before the first lock (_ensure_receipt_payment_entries),
after each has read the receipt's balance and planned its share - the CS-02273 window.
"""

import threading
from unittest.mock import patch

import frappe
from frappe.utils import flt

from klik_pos.api import mpesa
from klik_pos.tests.test_mpesa_receipt_balance import ReceiptCase

LOSER_MESSAGE = r"a moment ago"  # both refusal messages say it


def _till(site, sites_path, invoice_name, results):
	frappe.init(site=site, sites_path=sites_path)
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		summary = mpesa._allocate_receipts_before_submit(invoice)
		invoice.submit()
		mpesa._finalize_mpesa_reconciliation(invoice, summary)
		frappe.db.commit()
		results[invoice_name] = "submitted"
	except Exception as e:
		results[invoice_name] = e
		if getattr(frappe.local, "db", None):  # init/connect itself may be what failed
			frappe.db.rollback()
	finally:
		frappe.destroy()


def _purge(doctype, name):
	"""Delete a committed test document and its ledger rows; submitted ones are flipped to
	cancelled first because delete_doc refuses a submitted record."""
	if not frappe.db.exists(doctype, name):
		return
	for ledger in ("GL Entry", "Payment Ledger Entry"):
		frappe.db.delete(ledger, {"voucher_no": name})
	frappe.db.delete("Payment Entry Reference", {"reference_name": name})
	frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
	frappe.delete_doc(doctype, name, force=1, ignore_permissions=True, delete_permanently=True)


class TestTwoTillsOneReceipt(ReceiptCase):
	@classmethod
	def tearDownClass(cls):
		# setUpClass db_inserts these settings; the first commit below made them permanent.
		frappe.db.delete("Mpesa Settings", {"business_shortcode": cls.shortcode})
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		self.created = []  # (doctype, name), purged in reverse

	def tearDown(self):
		frappe.db.rollback()
		# Entries are found by receipt, not only by _entries(): a test that fails before
		# reaching it must not leave them behind.
		registers = [n for t, n in self.created if t == "Mpesa C2B Payment Register"]
		for transid in frappe.get_all("Mpesa C2B Payment Register", {"name": ["in", registers or [""]]}, pluck="transid"):
			self._entries_for(transid)
		for doctype, name in reversed(self.created):
			_purge(doctype, name)
		frappe.db.commit()

	def _track(self, doc):
		self.created.append((doc.doctype, doc.name))
		return doc

	def _race(self, *invoices):
		site, sites_path, results = frappe.local.site, frappe.local.sites_path, {}
		barrier = threading.Barrier(len(invoices), timeout=30)
		real = mpesa._ensure_receipt_payment_entries

		def held(invoice):
			barrier.wait()
			return real(invoice)

		with patch.object(mpesa, "_ensure_receipt_payment_entries", held):
			threads = [
				threading.Thread(target=_till, args=(site, sites_path, i.name, results)) for i in invoices
			]
			for t in threads:
				t.start()
			for t in threads:
				t.join(90)
			# A till still running would commit after tearDown purged, leaving rows behind.
			self.assertFalse(any(t.is_alive() for t in threads), "a till never finished")
		frappe.db.commit()  # drop the main connection's pre-race snapshot
		return results

	def _setup(self, receipt_amount, used_first, sales):
		receipt = self._track(self._receipt(receipt_amount))
		if used_first:
			self._track(self._sell(used_first, receipt))
		drafts = [self._track(self._record(self._draft(rate=rate), receipt)) for rate in sales]
		frappe.db.commit()
		return receipt, drafts

	def _entries_for(self, transid, docstatus=None):
		filters = {"custom_mpesa_receipt_number": transid}
		if docstatus is not None:
			filters["docstatus"] = docstatus
		names = frappe.get_all("Payment Entry", filters, pluck="name")
		for name in names:
			if ("Payment Entry", name) not in self.created:
				self.created.insert(0, ("Payment Entry", name))  # purge after the invoices
		return names

	def _entries(self, receipt):
		return self._entries_for(receipt.transid, docstatus=1)

	def _assert_money_holds(self, receipt):
		entries = self._entries(receipt)
		self.assertEqual(len(entries), 1, "one receipt, one entry")
		self.assertGreaterEqual(flt(frappe.db.get_value("Payment Entry", entries[0], "unallocated_amount")), 0)
		invoices = [n for t, n in self.created if t == "Sales Invoice"]
		for name in frappe.get_all("Sales Invoice", {"name": ["in", invoices], "docstatus": 1}, pluck="name"):
			self.assertLessEqual(
				flt(frappe.db.get_value("Sales Invoice", name, "outstanding_amount")), 0.01, f"{name} posted short"
			)

	def _one_winner(self, results):
		won = [k for k, v in results.items() if v == "submitted"]
		lost = {k: v for k, v in results.items() if v != "submitted"}
		self.assertEqual(len(won), 1, f"expected one winner: {results}")
		((loser, error),) = lost.items()
		self.assertIsInstance(error, frappe.ValidationError, f"loser failed the wrong way: {error!r}")
		self.assertRegex(str(error), LOSER_MESSAGE)
		self.assertEqual(frappe.db.get_value("Sales Invoice", loser, "docstatus"), 0)
		return loser

	def _retry(self, loser):
		return self._race(frappe.get_doc("Sales Invoice", loser))[loser]

	def test_new_receipt_too_small_for_both(self):
		receipt, drafts = self._setup(1000, 0, [800, 800])
		loser = self._one_winner(self._race(*drafts))
		self.assertRegex(str(self._retry(loser)), LOSER_MESSAGE)
		self._assert_money_holds(receipt)

	def test_open_receipt_too_small_for_both(self):
		receipt, drafts = self._setup(1000, 200, [800, 800])
		loser = self._one_winner(self._race(*drafts))
		self.assertRegex(str(self._retry(loser)), LOSER_MESSAGE)
		self._assert_money_holds(receipt)

	def test_receipt_big_enough_for_both_lets_the_retry_through(self):
		receipt, drafts = self._setup(1000, 0, [300, 300])
		loser = self._one_winner(self._race(*drafts))
		self.assertEqual(self._retry(loser), "submitted")
		self._assert_money_holds(receipt)
		self.assertEqual(flt(frappe.db.get_value("Payment Entry", self._entries(receipt)[0], "unallocated_amount")), 400)
