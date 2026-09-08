import json

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from klik_pos.api.sales_invoice import (
    _apply_extra_fields,
    _apply_walkin_party_fields,
    _get_active_pos_profile,
    _parse_extra_fields,
    get_current_pos_opening_entry,
    parse_invoice_data,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_held_order_access(so):
    """Ensure the SO is a KLiK held order the current user/session may act on.

    In order: it must be a held order at all; System Managers bypass the rest. Then it
    must belong to the caller's active shift, or be stranded on their own till with no live
    shift behind it, or - when the caller has no shift open - simply be theirs. Anyone
    else's work is allowed only on a till whose POS Profile permits it, which is the same
    rule the Draft tab lists by.
    """
    if not so.custom_is_klik_held:
        frappe.throw(_("Order {0} is not a KLiK held order.").format(so.name))

    if "System Manager" in frappe.get_roles():
        return

    opening_entry = get_current_pos_opening_entry()
    if opening_entry:
        if so.custom_pos_opening_entry == opening_entry:
            return
        if _is_orphaned_on_this_till(so) and _may_act_on_others_work(so):
            # Stranded on this counter by an earlier session. Refusing it left the order
            # unusable by anyone but a System Manager while still sitting in the Draft tab,
            # so the cashier who found it could neither serve it nor clear it.
            return
        frappe.throw(_("You are not allowed to access held order {0}.").format(so.name))
    elif not _may_act_on_others_work(so):
        frappe.throw(_("You are not allowed to access held order {0}.").format(so.name))


def _may_act_on_others_work(so):
    """Your own order always; someone else's only where the till allows it.

    The same rule the Draft tab lists by, so a cashier is never shown an order they are then
    refused when they tap it.
    """
    return so.owner == frappe.session.user or _till_allows_other_cashiers()


def _is_orphaned_on_this_till(so):
    """Whether this held order belongs to the caller's till but to no live shift."""
    try:
        pos_doc = _get_active_pos_profile()
    except Exception:
        return False

    profile = getattr(pos_doc, "name", None)
    if not profile or so.custom_pos_profile != profile:
        return False

    if not so.custom_pos_opening_entry:
        return True
    status = frappe.db.get_value("POS Opening Entry", so.custom_pos_opening_entry, "status")
    return status != "Open"


def _build_cart_meta(data, parsed_items, business_type, salesperson, tax_id,
                     delivery_charge, delivery_personnel, sales_and_tax_charges, roundoff_amount):
    """Serialise all POS-specific cart state that doesn't live on the SO itself."""
    raw_discounts = data.get("itemDiscounts", {}) if isinstance(data, dict) else {}
    item_discounts = {}

    for item in parsed_items:
        item_code = item["id"]
        discount_data = raw_discounts.get(item_code) or {}
        if isinstance(discount_data, str):
            try:
                discount_data = json.loads(discount_data)
            except Exception:
                discount_data = {}

        item_discounts[item_code] = {
            "discountPercentage": flt(item.get("discountPercentage") or 0),
            "discountAmount": flt(item.get("discountAmount") or 0),
            "customRate": discount_data.get("customRate"),
            "customRateIncludesTax": bool(discount_data.get("customRateIncludesTax")),
            "bundle_entries": item.get("bundle_entries") or [],
            "item_tax_template": item.get("item_tax_template") or "",
            "item_tax_rate": item.get("item_tax_rate") or {},
        }

    # Persist the full frontend customer object (if sent) so resume can restore it
    # directly, without a re-fetch + re-transform round-trip.
    customer_data = data.get("customerData") if isinstance(data, dict) else None
    if isinstance(customer_data, str):
        try:
            customer_data = json.loads(customer_data)
        except Exception:
            customer_data = None

    return {
        "itemDiscounts": item_discounts,
        "appliedCoupons": data.get("appliedCoupons") or [] if isinstance(data, dict) else [],
        "businessType": business_type or "B2C",
        "salesperson": salesperson,
        "tax_id": tax_id,
        "deliveryCharge": flt(delivery_charge),
        "deliveryPersonnel": delivery_personnel,
        "SalesTaxCharges": sales_and_tax_charges,
        "roundOffAmount": flt(roundoff_amount),
        "customer": customer_data,
        "walkin_name": data.get("walkin_name") if isinstance(data, dict) else None,
        "walkin_phone": data.get("walkin_phone") if isinstance(data, dict) else None,
        "extra_fields": _parse_extra_fields(data),
    }


def _apply_order_discount(so, pos_profile, order_discount_amount):
    """Set the Sales Order's native additional-discount fields, gated by the
    POS Profile's Allow Discount Change permission (same flag used for the
    Sales Invoice's order-level discount)."""
    order_discount_amount = flt(order_discount_amount or 0)
    if order_discount_amount < 0:
        frappe.throw(_("Discount amount cannot be negative."))
    if order_discount_amount > 0:
        if not cint(getattr(pos_profile, "allow_discount_change", 0) or 0):
            frappe.throw(_("Discount changes are not allowed for this POS Profile."))
        so.apply_discount_on = "Grand Total"
        so.discount_amount = order_discount_amount
    else:
        so.apply_discount_on = ""
        so.discount_amount = 0


def _build_sales_order_doc(customer, items, sales_and_tax_charges, cart_meta, order_discount_amount=0.0):
    """Create a new draft Sales Order from parsed cart data."""
    pos_profile = _get_active_pos_profile()
    opening_entry = get_current_pos_opening_entry() or ""
    warehouse = getattr(pos_profile, "warehouse", "") or ""

    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.order_type = "Sales"
    so.transaction_date = nowdate()
    so.delivery_date = nowdate()
    so.company = pos_profile.company
    so.currency = pos_profile.currency
    so.selling_price_list = pos_profile.selling_price_list
    so.taxes_and_charges = sales_and_tax_charges or getattr(pos_profile, "taxes_and_charges", "") or ""
    so.custom_pos_profile = pos_profile.name
    so.custom_pos_opening_entry = opening_entry
    so.custom_is_klik_held = 1
    so.custom_klik_cart_meta = json.dumps(cart_meta)

    _apply_order_discount(so, pos_profile, order_discount_amount)

    if cart_meta.get("tax_id") and so.meta.has_field("tax_id"):
        so.tax_id = cart_meta.get("tax_id")
    _apply_walkin_party_fields(
        so,
        walkin_name=cart_meta.get("walkin_name"),
        walkin_phone=cart_meta.get("walkin_phone"),
    )
    _apply_extra_fields(so, cart_meta.get("extra_fields"))

    for item in items:
        so.append("items", {
            "item_code": item["id"],
            "qty": flt(item.get("quantity") or 1),
            "rate": flt(item.get("price") or 0),
            "uom": item.get("uom") or "",
            "delivery_date": nowdate(),
            "warehouse": warehouse,
        })

    so.set_missing_values()
    so.calculate_taxes_and_totals()
    return so


def _rebuild_sales_order(so, customer, items, sales_and_tax_charges, cart_meta, order_discount_amount=0.0):
    """Overwrite an existing held Sales Order with refreshed cart data."""
    pos_profile = _get_active_pos_profile()
    warehouse = getattr(pos_profile, "warehouse", "") or ""

    so.customer = customer
    so.delivery_date = nowdate()
    so.taxes_and_charges = sales_and_tax_charges or getattr(pos_profile, "taxes_and_charges", "") or ""
    so.set("items", [])

    _apply_order_discount(so, pos_profile, order_discount_amount)

    if cart_meta.get("tax_id") and so.meta.has_field("tax_id"):
        so.tax_id = cart_meta.get("tax_id")
    _apply_walkin_party_fields(
        so,
        walkin_name=cart_meta.get("walkin_name"),
        walkin_phone=cart_meta.get("walkin_phone"),
    )
    _apply_extra_fields(so, cart_meta.get("extra_fields"))

    for item in items:
        so.append("items", {
            "item_code": item["id"],
            "qty": flt(item.get("quantity") or 1),
            "rate": flt(item.get("price") or 0),
            "uom": item.get("uom") or "",
            "delivery_date": nowdate(),
            "warehouse": warehouse,
        })

    so.set_missing_values()
    so.calculate_taxes_and_totals()


# ---------------------------------------------------------------------------
# Whitelisted API endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_held_order(data):
    """Create or update a held Sales Order from the POS cart."""
    try:
        if isinstance(data, str):
            data = json.loads(data)

        from klik_pos.api.pos_profile import validate_required_extra_fields
        validate_required_extra_fields(_parse_extra_fields(data))

        target_order_id = data.get("held_order_id") if isinstance(data, dict) else None

        # Every field is named, even the unused ones. Collapsing them to `_` rebound the
        # translation function imported at the top of this module, so the frappe.throw below
        # raised "'NoneType' object is not callable" instead of its own message - and the
        # except block reported that to the cashier as the reason their order would not hold.
        (
            customer,
            items,
            _amount_paid,
            sales_and_tax_charges,
            _mode_of_payment,
            business_type,
            roundoff_amount,
            delivery_charge,
            delivery_personnel,
            _is_credit_sale,
            _allow_partial_payment,
            _due_date,
            salesperson,
            tax_id,
            _enable_background_submission,
            _loyalty_redemption,
        ) = parse_invoice_data(data)

        cart_meta = _build_cart_meta(
            data, items, business_type, salesperson, tax_id,
            delivery_charge, delivery_personnel, sales_and_tax_charges, roundoff_amount,
        )
        order_discount_amount = flt(data.get("orderDiscountAmount") or 0) if isinstance(data, dict) else 0

        if target_order_id:
            so = frappe.get_doc("Sales Order", target_order_id)
            if so.docstatus != 0:
                frappe.throw(_("Cannot update held order {0}: it is no longer a draft.").format(target_order_id))
            _rebuild_sales_order(so, customer, items, sales_and_tax_charges, cart_meta, order_discount_amount)
            so.custom_klik_cart_meta = json.dumps(cart_meta)
            so.save(ignore_permissions=True)
        else:
            so = _build_sales_order_doc(customer, items, sales_and_tax_charges, cart_meta, order_discount_amount)
            so.insert(ignore_permissions=True)

        return {"success": True, "order_name": so.name}

    except Exception as e:
        # Roll back BEFORE logging, and never return without rolling back.
        # so.insert() assigns the Sales Order name - incrementing the Document Naming Rule
        # counter - before it validates, so swallowing the exception without a rollback
        # lets Frappe's request handler commit that increment while no order exists. The
        # order number is then burned permanently. This is the same defect that cost
        # production 38 POS receipt numbers in Sept 2026; see the "naming-counter burn
        # guard" comment in api/sales_invoice.py for the full mechanism.
        # The Error Log row must be written after the rollback or it is discarded with it.
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Held Order Error")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_held_order_details(order_id):
    """Return items, customer and cart metadata for resuming a held order."""
    try:
        so = frappe.get_doc("Sales Order", order_id)
        _assert_held_order_access(so)

        cart_meta = {}
        if so.custom_klik_cart_meta:
            try:
                cart_meta = json.loads(so.custom_klik_cart_meta)
            except Exception:
                pass

        item_discounts = cart_meta.get("itemDiscounts", {})

        # Batch-fetch item names
        item_codes = [row.item_code for row in so.items]
        item_names = {}
        if item_codes:
            rows = frappe.get_all(
                "Item",
                filters={"name": ["in", item_codes]},
                fields=["name", "item_name"],
            )
            item_names = {r.name: r.item_name for r in rows}

        items = []
        for row in so.items:
            d = item_discounts.get(row.item_code) or {}
            items.append({
                "item_code": row.item_code,
                "item_name": item_names.get(row.item_code) or row.item_code,
                "quantity": flt(row.qty),
                "price": flt(row.rate),
                "uom": row.uom or "",
                "discountAmount": flt(d.get("discountAmount") or 0),
                "discountPercentage": flt(d.get("discountPercentage") or 0),
                "customRate": d.get("customRate"),
                "customRateIncludesTax": bool(d.get("customRateIncludesTax")),
                "bundle_entries": d.get("bundle_entries") or [],
                "item_tax_template": d.get("item_tax_template") or "",
                "item_tax_rate": d.get("item_tax_rate") or {},
            })

        return {
            "success": True,
            "name": so.name,
            "customer": so.customer,
            "customer_data": cart_meta.get("customer"),
            "walkin_name": cart_meta.get("walkin_name"),
            "walkin_phone": cart_meta.get("walkin_phone"),
            "extra_fields": cart_meta.get("extra_fields") or {},
            "items": items,
            "cart_meta": cart_meta,
            "grand_total": flt(so.grand_total),
            "currency": so.currency,
            "discount_amount": flt(so.discount_amount or 0),
            "apply_discount_on": so.apply_discount_on or "",
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Held Order Details Error")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def delete_held_order(order_id):
    """Delete a held (draft) Sales Order."""
    try:
        so = frappe.get_doc("Sales Order", order_id)
        _assert_held_order_access(so)
        if so.docstatus != 0:
            return {"success": False, "error": f"Cannot delete {order_id}: not a draft."}
        so.delete(ignore_permissions=True)
        return {"success": True, "message": f"Held order {order_id} deleted."}
    except frappe.DoesNotExistError:
        return {"success": False, "error": f"Order {order_id} not found."}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Delete Held Order Error: {order_id}")
        return {"success": False, "error": str(e)}


def _till_allows_other_cashiers():
    """Whether this till lets its users see held orders they did not ring.

    Delegates to the same helper Invoice History uses for invoices, so the two surfaces
    cannot drift into disagreeing about what one POS Profile setting means. A till with no
    resolvable profile reads as "no", which is the behaviour the page had before the flag
    existed.
    """
    from klik_pos.api.sales_invoice import _profile_allows_other_cashiers

    try:
        pos_doc = _get_active_pos_profile()
    except Exception:
        return False
    return _profile_allows_other_cashiers(pos_doc)


def _attach_cashier_names(orders):
    """Add each order's owner full name, the identity the history filters compare against."""
    owners = {o.get("owner") for o in orders if o.get("owner")}
    names = {}
    if owners:
        names = {
            row.name: row.full_name
            for row in frappe.get_all(
                "User", filters={"name": ["in", list(owners)]}, fields=["name", "full_name"]
            )
        }
    for order in orders:
        order["cashier_name"] = names.get(order.get("owner")) or order.get("owner") or ""
    return orders


@frappe.whitelist()
def get_held_orders(limit=50, start=0, search="", skip_opening_entry_filter=False):
    """List held Sales Orders.

    By default lists held orders for the current POS session (used by the
    Closing Shift page). When ``skip_opening_entry_filter`` is true (used by the
    Invoice History page), the opening-entry restriction is dropped and results are
    scoped the same way ``get_sales_invoices`` scopes its history surface: an
    Administrator or System Manager sees all, and so does everyone on a till whose
    POS Profile sets ``custom_allow_viewing_other_cashiers``; otherwise you see your own.

    That flag used to be read for invoices and ignored here, so a shop that had
    deliberately opened its till up still found the Draft tab showing one cashier's
    held orders and nobody else's.

    Each row carries ``cashier_name`` - the owner's full name, which is the identity
    Invoice History filters on. Returning only the email made every held order fail the
    comparison against a cashier filter holding a full name, so a cashier restricted to
    their own work saw an empty Draft tab rather than their own held orders.
    """
    try:
        if isinstance(skip_opening_entry_filter, str):
            skip_opening_entry_filter = skip_opening_entry_filter.lower() in ("true", "1", "yes")

        limit = int(limit) if limit else 50
        start = int(start) if start else 0
        is_admin_user = "System Manager" in frappe.get_roles() or "Administrator" in frappe.get_roles()
        may_see_other_cashiers = is_admin_user or _till_allows_other_cashiers()

        filters = {"custom_is_klik_held": 1, "docstatus": 0}
        if skip_opening_entry_filter:
            if not may_see_other_cashiers:
                filters["owner"] = frappe.session.user
        else:
            opening_entry = get_current_pos_opening_entry()
            if opening_entry:
                filters["custom_pos_opening_entry"] = opening_entry
            elif not may_see_other_cashiers:
                # No active session — only show the caller's own held orders, unless the
                # till is one that lets its users see each other's.
                filters["owner"] = frappe.session.user

        orders = frappe.get_all(
            "Sales Order",
            filters=filters,
            fields=[
                "name", "customer", "customer_name", "transaction_date",
                "grand_total", "currency", "owner", "modified",
                "custom_pos_profile", "custom_pos_opening_entry",
            ],
            order_by="modified desc",
            limit=limit,
            start=start,
        )

        if search and search.strip():
            term = search.strip().lower()
            orders = [
                o for o in orders
                if term in (o.name or "").lower()
                or term in (o.customer_name or "").lower()
                or term in (o.customer or "").lower()
            ]

        _attach_cashier_names(orders)

        order_names = [o.name for o in orders]
        items_map = {}
        if order_names:
            all_items = frappe.get_all(
                "Sales Order Item",
                filters={"parent": ["in", order_names]},
                fields=["parent", "item_code", "item_name", "qty", "rate"],
            )
            for row in all_items:
                items_map.setdefault(row.parent, []).append({
                    "item_code": row.item_code,
                    "item_name": row.item_name,
                    "qty": flt(row.qty),
                    "rate": flt(row.rate),
                })

        # Resolve cashier (owner full name) so rows render/filter like invoices.
        owner_ids = list({o.owner for o in orders if o.owner})
        cashier_map = {}
        if owner_ids:
            for row in frappe.get_all(
                "User", filters={"name": ["in", owner_ids]}, fields=["name", "full_name"]
            ):
                cashier_map[row.name] = row.full_name

        for order in orders:
            order["status"] = "Draft"
            order["items"] = items_map.get(order.name, [])
            order["cashier"] = cashier_map.get(order.owner) or order.owner

        return {"success": True, "data": orders, "total_count": len(orders)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Held Orders Error")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def checkout_held_order(order_id, data=None):
    """
    Convert a held Sales Order into a submitted Sales Invoice.
    Accepts the same checkout payload as create_and_submit_invoice.
    Deletes the Sales Order on success.
    """
    try:
        if data and isinstance(data, str):
            data = json.loads(data)

        # Answer a replay before touching the Sales Order: a successful first call already
        # deleted it, so loading it here would fail the retry instead of returning the
        # invoice that first call created.
        from klik_pos.api.sales_invoice import (
            _checkout_request_response,
            _get_checkout_request,
            _normalize_checkout_request_id,
        )

        checkout_request_id = _normalize_checkout_request_id(
            (data or {}).get("checkout_request_id")
        )
        existing_checkout = _get_checkout_request(checkout_request_id)
        if existing_checkout:
            return _checkout_request_response(existing_checkout)

        so = frappe.get_doc("Sales Order", order_id)
        _assert_held_order_access(so)
        if so.docstatus != 0:
            frappe.throw(_("Sales Order {0} is not a draft.").format(order_id))

        # Reuse the full invoice submission pipeline
        from klik_pos.api.sales_invoice import queue_sales_invoice
        result = queue_sales_invoice(data)

        if result.get("success"):
            # SO fulfilled — remove it so it doesn't clutter held orders list
            try:
                frappe.delete_doc("Sales Order", order_id, ignore_permissions=True)
            except Exception as del_err:
                frappe.logger().warning(
                    "Could not delete held SO %s after checkout: %s", order_id, del_err
                )

        return result

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Checkout Held Order Error: {order_id}")
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Internal — called from pos_entry.py on shift close
# ---------------------------------------------------------------------------

def _orphaned_held_orders(opening_entry_name):
    """Held orders on this till that no shift close will ever reach.

    An order held while no shift was open is stamped with an empty opening entry, because
    that is what get_current_pos_opening_entry returns then. The sweep below matches on the
    opening entry, so those orders were never swept by anything: they sat in the Draft tab
    for good, and a cashier in a later shift could not even open them.

    Also collected: orders pointing at an opening entry that has since been closed or
    deleted, which are stranded for the same reason.

    Two guards keep this from reaching into work that is still live. The order must be on
    the same till as the shift being closed, and it must predate that shift - anything held
    since this shift opened would have been stamped with it, so an unstamped newer order
    belongs to a session this close knows nothing about.
    """
    entry = frappe.db.get_value(
        "POS Opening Entry", opening_entry_name, ["pos_profile", "period_start_date"], as_dict=True
    )
    if not entry or not entry.pos_profile or not entry.period_start_date:
        return []

    rows = frappe.db.sql(
        """
        SELECT so.name
        FROM `tabSales Order` so
        LEFT JOIN `tabPOS Opening Entry` ope ON ope.name = so.custom_pos_opening_entry
        WHERE so.custom_is_klik_held = 1
          AND so.docstatus = 0
          AND so.custom_pos_profile = %(profile)s
          AND so.modified < %(started)s
          AND (
                so.custom_pos_opening_entry IS NULL
                OR so.custom_pos_opening_entry = ''
                OR ope.name IS NULL
                OR ope.status = 'Closed'
              )
        """,
        {"profile": entry.pos_profile, "started": entry.period_start_date},
        as_dict=True,
    )
    return [row.name for row in rows]


def delete_held_orders_for_opening_entry(opening_entry_name):
    """Delete the held Sales Orders a shift close is responsible for.

    That is this session's own held orders, plus any stranded on the same till by an earlier
    session that could never be swept - see _orphaned_held_orders.
    """
    try:
        names = frappe.get_all(
            "Sales Order",
            filters={
                "custom_is_klik_held": 1,
                "docstatus": 0,
                "custom_pos_opening_entry": opening_entry_name,
            },
            pluck="name",
        )
        for name in _orphaned_held_orders(opening_entry_name):
            if name not in names:
                names.append(name)
        deleted = 0
        for name in names:
            try:
                frappe.delete_doc("Sales Order", name, ignore_permissions=True)
                deleted += 1
            except Exception as e:
                frappe.logger().error("Error deleting held order %s: %s", name, e)
        if deleted:
            frappe.logger().info(
                "Cleared %d held order(s) for opening entry %s", deleted, opening_entry_name
            )
        return deleted
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Clear Held Orders on POS Close")
        return 0
