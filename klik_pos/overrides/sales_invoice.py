import frappe

from klik_pos.api.sales_invoice import validate_required_salesperson


def validate_sales_person_on_submit(doc, method=None):
    """
    Check if Sales Person is required for POS transactions and validate before submitting the Sales Invoice
    """
    validate_required_salesperson(doc)


def set_sale_type(doc, method=None):
    """before_insert: every invoice is Cash or Credit. klik's till sets it (Credit Sale ->
    Credit); the desk form's choice stands (default Cash). A return follows its original.
    Before insert because sites name invoices from it (Allparts: CS- / INV-)."""
    if doc.get("is_return") and doc.get("return_against"):
        doc.custom_sale_type = (
            frappe.db.get_value("Sales Invoice", doc.return_against, "custom_sale_type") or "Cash"
        )
    elif not doc.get("custom_sale_type"):
        doc.custom_sale_type = "Cash"


def require_payment_for_cash_sale(doc, method=None):
    """before_submit: a Cash sale is fully paid - on the invoice (POS payments) or by
    advances, or by a customer-credit voucher that checkout applies right after submit
    (_klik_customer_credit). A till sale left part paid is a Credit sale. Only desk/API
    submissions are checked; scripts, tests and background jobs have no request."""
    credit = frappe.utils.flt(getattr(doc, "_klik_customer_credit", 0))
    unpaid = frappe.utils.flt(doc.outstanding_amount) - credit
    if (
        doc.get("custom_sale_type") == "Cash"
        and not doc.get("is_return")
        and not doc.get("is_consolidated")
        and getattr(frappe.local, "request", None)
        and frappe.utils.flt(unpaid, 2) > 0
    ):
        frappe.throw(
            frappe._(
                "Cash Sales require full payment before submission. Receive the payment, "
                "or make this a Credit sale."
            )
        )
