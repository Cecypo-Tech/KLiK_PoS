import frappe
from frappe import _


def remove_duplicate_sales_persons(doc, method=None):
    seen = set()
    unique = []

    for row in doc.custom_sales_person:
        if row.sales_person not in seen:
            seen.add(row.sales_person)
            unique.append(row)
        else:
            frappe.msgprint(
                _("Duplicate Sales Person {0} removed.").format(row.sales_person),
                alert=True,
            )

    doc.custom_sales_person = unique


def change_account_mismatches(doc):
    """(mode_of_payment, account) for each Cash mode on the till whose account is not the
    till's change account - or, when that is blank, the company's default cash account,
    which is what ERPNext falls back to (set_pos_fields)."""
    change_account = doc.account_for_change_amount or frappe.get_cached_value(
        "Company", doc.company, "default_cash_account"
    )
    out = []
    for row in doc.get("payments") or []:
        if frappe.get_cached_value("Mode of Payment", row.mode_of_payment, "type") != "Cash":
            continue
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": row.mode_of_payment, "company": doc.company},
            "default_account",
        )
        if account and account != change_account:
            out.append((row.mode_of_payment, account))
    return out


def warn_change_account_mismatch(doc, method=None):
    """Warn - not block: a till taking cash into several accounts can only match one.

    With POS Settings "post change GL entries" off, ERPNext takes change only off the payment
    row booked to the change account, so change on any other cash account is never posted
    and sits as customer credit; with it on, the change comes out of the wrong drawer."""
    mismatches = change_account_mismatches(doc)
    if not mismatches:
        return
    change_account = doc.account_for_change_amount or frappe.get_cached_value(
        "Company", doc.company, "default_cash_account"
    )
    rows = "".join(
        "<li>{0} &rarr; {1}</li>".format(frappe.bold(mode), frappe.bold(account))
        for mode, account in mismatches
    )
    frappe.msgprint(
        _(
            "The Change Account is {0}, but these cash payment modes post to a different account:"
            "<ul>{1}</ul>Change given on them will not come out of that drawer. Set Change Account"
            " to the till's cash account."
        ).format(frappe.bold(change_account or _("not set")), rows),
        title=_("Change Account mismatch"),
        indicator="orange",
    )
