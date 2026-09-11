"""A held order a cashier can see is one they can open, and the other way round.

Production (SO-00037): a Sales User tapped a held order in the Held tab and was told "You are
not allowed to access held order". Nothing to do with their Sales Order permissions - the two
surfaces ran different rules. The tab listed every order that was theirs, or everyone's where
the till allows it, with no regard to shift or till. Opening one, with a shift open, demanded
the caller's own current shift or an orphan on their own till. So another cashier's order on a
shift still open, or the caller's own order on another till, was listed and then refused.

One rule now decides both: the order is on the caller's till (or carries no till at all), and it
is theirs or the till lets its users act on each other's work. The shift that held it no longer
matters - handing an order from the front desk to the counter is what the till setting is for.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.sales_order import (
	_assert_held_order_access,
	checkout_held_order,
	create_held_order,
	get_held_orders,
)
from klik_pos.tests.test_held_order_orphans import _held_order, _opening_entry

TILL = "_Test POS Profile"
OTHER_TILL = "QA Shift Scenarios"
SOMEONE_ELSE = "somebody-else@example.com"
MY_SHIFT = "POS-OPE-MINE"


def _till(allow_others):
	return frappe._dict({"name": TILL, "custom_allow_viewing_other_cashiers": allow_others})


@contextmanager
def _as_cashier(till, opening_entry=MY_SHIFT):
	"""A Sales User standing at `till` (None: no till resolvable) with `opening_entry` open."""
	profile_patch = (
		patch.object(sales_order, "_get_active_pos_profile", side_effect=Exception("no till"))
		if till is None
		else patch.object(sales_order, "_get_active_pos_profile", return_value=till)
	)
	with ExitStack() as stack:
		stack.enter_context(patch("frappe.get_roles", return_value=["All", "Sales User"]))
		stack.enter_context(profile_patch)
		stack.enter_context(
			patch.object(sales_order, "get_current_pos_opening_entry", return_value=opening_entry)
		)
		yield


def _listed(so):
	result = get_held_orders(skip_opening_entry_filter=True, limit=5000)
	assert result["success"], result.get("error")
	return so.name in [row["name"] for row in result["data"]]


def _allowed(so):
	try:
		_assert_held_order_access(so)
		return True
	except frappe.ValidationError:
		return False


def _order(**kwargs):
	# Newest first in the listing, so the limit can never push a test order out of it.
	kwargs.setdefault("minutes_ago", 0)
	return _held_order(**kwargs)


class TestOneRuleForListingAndOpening(FrappeTestCase):
	def _assert_both(self, so, till, expected, opening_entry=MY_SHIFT):
		with _as_cashier(till, opening_entry):
			listed, allowed = _listed(so), _allowed(so)
		self.assertEqual(
			(listed, allowed), (expected, expected), f"listed={listed} allowed={allowed}"
		)

	def test_another_cashier_s_order_on_their_live_shift_opens_where_the_till_allows_it(self):
		"""The regression: SO-00037, listed in the Held tab and refused when tapped."""
		live = _opening_entry(hours_ago=1)
		theirs = _order(opening_entry=live.name, owner=SOMEONE_ELSE)

		self._assert_both(theirs, _till(1), True)

	def test_another_cashier_s_order_is_neither_listed_nor_opened_on_a_closed_till(self):
		live = _opening_entry(hours_ago=1)
		theirs = _order(opening_entry=live.name, owner=SOMEONE_ELSE)

		self._assert_both(theirs, _till(0), False)

	def test_my_own_order_on_another_till_is_neither_listed_nor_opened(self):
		"""Listed and then refused, before. Another till can be another warehouse or company."""
		elsewhere = _order(opening_entry="", profile=OTHER_TILL)

		self._assert_both(elsewhere, _till(1), False)

	def test_my_order_on_a_shift_still_open_at_another_till_is_neither_listed_nor_opened(self):
		live = _opening_entry(hours_ago=1)
		elsewhere = _order(opening_entry=live.name, profile=OTHER_TILL)

		self._assert_both(elsewhere, _till(1), False)

	def test_my_order_in_my_current_shift_is_listed_and_opened(self):
		mine = _order(opening_entry=MY_SHIFT)

		self._assert_both(mine, _till(0), True)

	def test_an_order_carrying_no_till_is_listed_and_opened_by_its_owner(self):
		"""Nothing sweeps these, so hiding them would strand them for good."""
		legacy = _order(opening_entry="", profile="")

		self._assert_both(legacy, _till(0), True)

	def test_with_no_till_resolvable_a_cashier_keeps_to_their_own(self):
		mine = _order(opening_entry="")
		theirs = _order(opening_entry="", owner=SOMEONE_ELSE)

		self._assert_both(mine, None, True, opening_entry=None)
		self._assert_both(theirs, None, False, opening_entry=None)

	def test_the_listing_and_the_open_check_never_disagree(self):
		"""The property that broke. Every order, every till setting, with and without a shift."""
		live = _opening_entry(hours_ago=1)
		orders = {
			"mine, my shift": _order(opening_entry=MY_SHIFT),
			"mine, other till": _order(opening_entry="", profile=OTHER_TILL),
			"mine, no till": _order(opening_entry="", profile=""),
			"theirs, live shift": _order(opening_entry=live.name, owner=SOMEONE_ELSE),
			"theirs, other till": _order(opening_entry=live.name, profile=OTHER_TILL, owner=SOMEONE_ELSE),
			"theirs, no till": _order(opening_entry="", profile="", owner=SOMEONE_ELSE),
		}

		for allow_others in (0, 1):
			for opening_entry in (MY_SHIFT, None):
				with _as_cashier(_till(allow_others), opening_entry):
					for label, so in orders.items():
						with self.subTest(order=label, allow_others=allow_others, shift=opening_entry):
							self.assertEqual(_listed(so), _allowed(so))


def _payload(held_order_id):
	return {
		"customer": {"id": "Walk In"},
		"items": [{"id": "Consulting", "item_code": "Consulting", "name": "Consulting", "quantity": 2, "price": 10, "uom": "Nos"}],
		"status": "held",
		"held_order_id": held_order_id,
	}


class TestReHoldingByIdIsChecked(FrappeTestCase):
	def test_a_sales_order_that_was_never_held_cannot_be_overwritten(self):
		"""The id came from the client and was loaded and saved with permissions ignored."""
		plain = _order(opening_entry=MY_SHIFT)
		frappe.db.set_value("Sales Order", plain.name, "custom_is_klik_held", 0, update_modified=False)

		with _as_cashier(_till(1)), patch.object(sales_order, "_rebuild_sales_order") as rebuild:
			result = create_held_order(_payload(plain.name))

		self.assertFalse(result["success"])
		self.assertIn("not a KLiK held order", result["message"])
		rebuild.assert_not_called()

	def test_an_order_from_another_till_cannot_be_re_held_here(self):
		elsewhere = _order(opening_entry="", profile=OTHER_TILL)

		with _as_cashier(_till(1)), patch.object(sales_order, "_rebuild_sales_order") as rebuild:
			result = create_held_order(_payload(elsewhere.name))

		self.assertFalse(result["success"])
		self.assertIn("not allowed to access held order", result["message"])
		rebuild.assert_not_called()

	def test_re_holding_a_handed_over_order_moves_it_to_my_shift_and_till(self):
		"""Otherwise the shift that first held it deletes it at close, from under whoever took it."""
		mine_now = frappe.get_all(
			"POS Opening Entry",
			filters={"user": "Administrator", "status": "Open", "docstatus": 1, "pos_profile": TILL},
			pluck="name",
			limit=1,
		)
		if not mine_now:
			self.skipTest(f"no open shift for Administrator on {TILL}")
		till = frappe.get_doc("POS Profile", TILL)
		till.custom_allow_viewing_other_cashiers = 1
		theirs = _order(opening_entry=_opening_entry(hours_ago=1).name, owner=SOMEONE_ELSE)
		legacy = _order(opening_entry="", profile="", owner=SOMEONE_ELSE)

		with _as_cashier(till, mine_now[0]):
			results = [create_held_order(_payload(so.name)) for so in (theirs, legacy)]

		for result, so in zip(results, (theirs, legacy), strict=True):
			self.assertTrue(result["success"], result.get("message"))
			stamped = frappe.db.get_value(
				"Sales Order", so.name, ["custom_pos_opening_entry", "custom_pos_profile"], as_dict=True
			)
			self.assertEqual((stamped.custom_pos_opening_entry, stamped.custom_pos_profile), (mine_now[0], TILL))


class TestCheckoutLocksTheOrder(FrappeTestCase):
	def test_the_order_is_locked_before_it_is_checked_or_invoiced(self):
		"""Two cashiers may now open one order; the second must wait, then find it gone."""
		so = _order(opening_entry=MY_SHIFT)
		calls = []

		with patch.object(sales_order, "_lock_held_order", side_effect=lambda name: calls.append("lock")), \
			patch.object(sales_order, "_assert_held_order_access", side_effect=lambda doc: calls.append("access")), \
			patch("klik_pos.api.sales_invoice.queue_sales_invoice", side_effect=lambda data: calls.append("queue") or {"success": False}):
			checkout_held_order(so.name, {})

		self.assertEqual(calls, ["lock", "access", "queue"])

	def test_a_second_cashier_finds_the_order_gone_rather_than_invoicing_it_again(self):
		from klik_pos.api.sales_order import _lock_held_order

		with self.assertRaises(frappe.DoesNotExistError):
			_lock_held_order("SO-KLIK-ALREADY-CHECKED-OUT")
