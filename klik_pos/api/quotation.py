import json

import frappe
from frappe.utils import add_days, add_months, cint, flt, nowdate

from klik_pos.api.sales_invoice import (
    _apply_extra_fields,
    _apply_pos_tax_treatment,
    _apply_remarks,
    _apply_walkin_party_fields,
    _get_active_pos_profile,
    _parse_extra_fields,
    _resolve_item_tax_details_for_line,
    parse_invoice_data,
    resolve_selling_price_list,
    set_line_price_list,
)
from klik_pos.api.sales_order import _apply_order_discount, _build_cart_meta

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _quote_item_row(q, pos_profile, item, warehouse):
    """A quote line: the whole ask, never split into stock and Loss of Sale, since a quote
    reserves nothing and is not limited by stock."""
    row = {
        "item_code": item["id"],
        "qty": (flt(item.get("quantity")) + flt(item.get("los_qty"))) or 1,
        "rate": flt(item.get("price") or 0),
        "uom": item.get("uom") or "",
        "warehouse": warehouse,
    }
    set_line_price_list(row, "Quotation Item", item.get("price_list"))
    item_tax_template, item_tax_rate = _resolve_item_tax_details_for_line(q, item, pos_profile)
    if item_tax_template:
        row["item_tax_template"] = item_tax_template
    if item_tax_rate:
        row["item_tax_rate"] = frappe.as_json(item_tax_rate)
    return row


def _build_quotation_doc(customer, items, sales_and_tax_charges, cart_meta, order_discount_amount=0.0):
    """A new draft Quotation from parsed cart data; mirrors sales_order._build_sales_order_doc."""
    pos_profile = _get_active_pos_profile()
    warehouse = getattr(pos_profile, "warehouse", "") or ""

    q = frappe.new_doc("Quotation")
    q.quotation_to = "Customer"
    q.party_name = customer
    # The shared helpers read doc.customer, which a Quotation does not have; this is a plain
    # attribute, not a field, so it is never saved.
    q.customer = customer
    q.order_type = "Sales"
    q.transaction_date = nowdate()
    # ERPNext only defaults valid_till in quotation.js on the desk form; mirror it here.
    days = cint(frappe.db.get_single_value("CRM Settings", "default_valid_till"))
    q.valid_till = add_days(q.transaction_date, days) if days else add_months(q.transaction_date, 1)
    q.company = pos_profile.company
    q.currency = pos_profile.currency
    q.selling_price_list = resolve_selling_price_list(cart_meta.get("selling_price_list"), None, pos_profile)
    q.custom_pos_profile = pos_profile.name
    q.custom_klik_cart_meta = json.dumps(cart_meta)
    # The cart already applied Pricing Rules; see sales_order._build_sales_order_doc.
    q.ignore_pricing_rule = 1

    _apply_order_discount(q, pos_profile, order_discount_amount)

    if cart_meta.get("tax_id") and q.meta.has_field("tax_id"):
        q.tax_id = cart_meta.get("tax_id")
    _apply_walkin_party_fields(
        q,
        walkin_name=cart_meta.get("walkin_name"),
        walkin_phone=cart_meta.get("walkin_phone"),
        walkin_tax_id=cart_meta.get("tax_id"),
    )
    _apply_extra_fields(q, cart_meta.get("extra_fields"))
    if cart_meta.get("remarks") is not None:
        _apply_remarks(q, {"remarks": cart_meta.get("remarks")})

    for item in items:
        q.append("items", _quote_item_row(q, pos_profile, item, warehouse))

    pos_line_prices = [(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in q.items]
    _apply_pos_tax_treatment(q, pos_profile, sales_and_tax_charges, pos_line_prices, restore_price_list_rate=False)
    return q


# ---------------------------------------------------------------------------
# Whitelisted API endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_quote(data):
    """Save the POS cart as a submitted Quotation. Not limited by stock."""
    try:
        if isinstance(data, str):
            data = json.loads(data)

        from klik_pos.api.pos_profile import validate_required_extra_fields

        validate_required_extra_fields(_parse_extra_fields(data))

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
        order_discount_amount = flt(data.get("orderDiscountAmount") or 0)

        q = _build_quotation_doc(customer, items, sales_and_tax_charges, cart_meta, order_discount_amount)
        q.insert(ignore_permissions=True)
        q.submit()

        # Quotation has no tax_id of its own to survive a save; held orders restore it the same way.
        if tax_id and q.meta.has_field("tax_id") and q.tax_id != tax_id:
            q.db_set("tax_id", tax_id)

        return {"success": True, "quote_name": q.name}

    except Exception as e:
        # Roll back before logging (the Error Log row would be discarded otherwise) and so the
        # naming counter taken by insert() is not committed for a quote that does not exist.
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Quote Error")
        return {"success": False, "message": str(e)}
