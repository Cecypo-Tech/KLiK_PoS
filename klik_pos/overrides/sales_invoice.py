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

