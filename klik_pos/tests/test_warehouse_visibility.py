"""With "Allow Viewing Other Cashiers" on, a till sees the work of every till selling from its warehouse.

Allparts runs three tills on one warehouse: a sales till (cash only, no returns), a floor
managers' till that returns the sales till's sales, and an admin till. Visibility was by
till - a non-manager's lists were held to their own till - so the floor managers could not
find the sales till's invoices to return them, nor its held orders to finish them. The
warehouse is the shop: tills sharing it see each other's invoices and held orders (with the
flag on); tills on another warehouse - another branch of the same company - do not.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice, sales_order
from klik_pos.api.sales_invoice import _may_read_row, get_sales_invoices
from klik_pos.api.sales_order import _may_act_on_held_order, get_held_orders
from klik_pos.tests.test_held_order_orphans import _held_order
from klik_pos.tests.test_opening_conflict import COMPANY, _profile

SHOP = "Stores - DC"
BRANCH = "Finished Goods - DC"
ME = "Administrator"
THEM = "warehouse-scope-other@example.com"


def _till_on(warehouse):
    name = _profile()
    frappe.db.set_value("POS Profile", name, {"warehouse": warehouse, "company": COMPANY})
    return name


def _till_doc(name, allow):
    return frappe._dict(
        {
            "name": name,
            "company": COMPANY,
            "warehouse": frappe.db.get_value("POS Profile", name, "warehouse"),
            "custom_allow_viewing_other_cashiers": allow,
        }
    )


def _invoice(till, owner=THEM, docstatus=1):
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = "Walk In"
    invoice.company = COMPANY
    invoice.append("items", {"item_code": "Consulting", "qty": 1, "rate": 10})
    invoice.insert(ignore_permissions=True)
    frappe.db.set_value(
        "Sales Invoice",
        invoice.name,
        {"pos_profile": till, "owner": owner, "docstatus": docstatus, "custom_pos_opening_entry": "POS-OPE-SCOPE"},
        update_modified=False,
    )
    return invoice.name


class Tills(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Warehouse", SHOP) or not frappe.db.exists("Warehouse", BRANCH):
            self.skipTest("needs two warehouses in Dev Co")
        self.mine, self.shop, self.branch = _till_on(SHOP), _till_on(SHOP), _till_on(BRANCH)


class TestOpeningAnInvoice(Tills):
    def _may(self, till, allow=1, docstatus=1, owner=THEM):
        return _may_read_row(owner, COMPANY, ME, _till_doc(self.mine, allow), docstatus=docstatus, pos_profile=till)

    def test_another_till_on_my_warehouse_opens_where_my_till_allows_it(self):
        self.assertTrue(self._may(self.shop))
        self.assertFalse(self._may(self.shop, allow=0))

    def test_a_till_on_another_warehouse_never_opens(self):
        self.assertFalse(self._may(self.branch))

    def test_drafts_follow_the_warehouse_too(self):
        self.assertTrue(self._may(self.shop, docstatus=0))
        self.assertFalse(self._may(self.branch, docstatus=0))

    def test_my_own_opens_anywhere(self):
        self.assertTrue(self._may(self.branch, allow=0, owner=ME))

    def test_an_invoice_rung_on_no_till_is_not_another_cashier_s_to_open(self):
        self.assertFalse(self._may(None))


@contextmanager
def _cashier_at(till_doc, roles=("Sales User",)):
    """A non-manager standing at `till_doc`: lists are held to the till for them."""
    with patch.object(sales_invoice, "get_current_pos_profile", return_value=till_doc), patch(
        "frappe.get_roles", return_value=list(roles)
    ):
        yield


class TestTheHistoryList(Tills):
    def test_a_cashier_sees_every_till_on_their_warehouse_and_no_other(self):
        on_shop, on_branch = _invoice(self.shop), _invoice(self.branch)

        with _cashier_at(_till_doc(self.mine, 1)):
            result = get_sales_invoices(limit=500, skip_opening_entry_filter=True, surface="history")

        self.assertTrue(result["success"], result.get("error"))
        names = {row["name"] for row in result["data"]}
        self.assertIn(on_shop, names)
        self.assertNotIn(on_branch, names)
        self.assertEqual([r["name"] for r in result["data"] if not r["can_open"]], [])

    def test_with_the_flag_off_only_my_own(self):
        on_shop = _invoice(self.shop)
        with _cashier_at(_till_doc(self.mine, 0)):
            result = get_sales_invoices(limit=500, skip_opening_entry_filter=True, surface="history")
        self.assertNotIn(on_shop, {row["name"] for row in result["data"]})


@contextmanager
def _standing_at(till_doc):
    with patch.object(sales_order, "_get_active_pos_profile", return_value=till_doc):
        yield


class TestHeldOrders(Tills):
    def test_another_till_s_order_on_my_warehouse_can_be_finished_here(self):
        theirs = _held_order(profile=self.shop, owner=THEM, minutes_ago=5)
        with _standing_at(_till_doc(self.mine, 1)):
            self.assertTrue(_may_act_on_held_order(theirs))
            listed = {row["name"] for row in get_held_orders(skip_opening_entry_filter=True, limit=5000)["data"]}
        self.assertIn(theirs.name, listed)

    def test_an_order_on_another_warehouse_stays_there(self):
        theirs = _held_order(profile=self.branch, owner=THEM, minutes_ago=5)
        with _standing_at(_till_doc(self.mine, 1)):
            self.assertFalse(_may_act_on_held_order(theirs))
            listed = {row["name"] for row in get_held_orders(skip_opening_entry_filter=True, limit=5000)["data"]}
        self.assertNotIn(theirs.name, listed)

    def test_with_the_flag_off_another_cashier_s_order_stays_theirs(self):
        theirs = _held_order(profile=self.shop, owner=THEM, minutes_ago=5)
        with _standing_at(_till_doc(self.mine, 0)):
            self.assertFalse(_may_act_on_held_order(theirs))

    def test_my_own_order_from_another_till_on_my_warehouse_is_mine_to_finish(self):
        mine = _held_order(profile=self.shop, owner=ME, minutes_ago=5)
        with _standing_at(_till_doc(self.mine, 0)):
            self.assertTrue(_may_act_on_held_order(mine))


class TestReturnsFollowTheWarehouse(Tills):
    """A sale from another branch could be picked and refunded here - its stock going back to
    the other branch's warehouse while the cash left this drawer."""

    def _till(self, allow=1):
        doc = _till_doc(self.mine, allow)
        doc.custom_allow_return = 1
        return doc

    def test_the_return_picker_lists_my_warehouse_and_not_another(self):
        from klik_pos.api.sales_invoice import get_customer_invoices_for_return

        on_shop, on_branch = _invoice(self.shop), _invoice(self.branch)
        with _cashier_at(self._till()), patch("klik_pos.klik_pos.utils.get_current_pos_profile", return_value=self._till()):
            result = get_customer_invoices_for_return("Walk In")
        self.assertTrue(result.get("success"), result)
        names = {row["name"] for row in result["data"]}
        self.assertIn(on_shop, names)
        self.assertNotIn(on_branch, names)

    def test_another_branch_s_sale_cannot_be_returned_here(self):
        from klik_pos.api.sales_invoice import return_sales_invoice

        on_branch = _invoice(self.branch)
        with _cashier_at(self._till()), patch("klik_pos.klik_pos.utils.get_current_pos_profile", return_value=self._till()):
            result = return_sales_invoice(on_branch)
        self.assertFalse(result.get("success"), result)
        self.assertIn("another branch", str(result.get("message") or result.get("error")))
        self.assertFalse(frappe.db.exists("Sales Invoice", {"return_against": on_branch}))


class TestDraftsFinishedElsewhere(Tills):
    def test_a_draft_finished_at_another_till_counts_in_that_till_s_shift(self):
        from klik_pos.api.sales_invoice import create_draft_invoice
        from klik_pos.tests.test_held_order_orphans import _opening_entry

        started, finished = _opening_entry(hours_ago=3), _opening_entry(hours_ago=1)
        payload = {
            "customer": {"id": "Walk In"},
            "items": [{"id": "Consulting", "item_code": "Consulting", "quantity": 1, "price": 100, "uom": "Nos"}],
            "status": "held",
        }
        with patch.object(sales_invoice, "get_current_pos_opening_entry", return_value=started.name):
            draft = create_draft_invoice(payload)
        self.assertTrue(draft["success"], draft.get("message"))
        with patch.object(sales_invoice, "get_current_pos_opening_entry", return_value=finished.name):
            create_draft_invoice({**payload, "draft_invoice_id": draft["invoice_name"]})
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", draft["invoice_name"], "custom_pos_opening_entry"), finished.name
        )

    def test_a_draft_with_an_stk_push_still_waiting_is_not_submitted(self):
        """The late M-Pesa payment would land on an invoice already finished with other money."""
        from klik_pos.api.sales_invoice import submit_draft_invoice
        from klik_pos.tests.test_held_order_mpesa_checkout import _draft, _stk_request

        draft = _draft()
        _stk_request(draft, "In Progress")
        result = submit_draft_invoice(draft.name)
        self.assertFalse(result["success"])
        self.assertEqual(frappe.db.get_value("Sales Invoice", draft.name, "docstatus"), 0)
