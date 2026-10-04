import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# POS Profile feature-toggle fields that are NOT covered by the auto-synced
# custom/pos_profile.json customization. These were previously created by a
# one-time patch (allow_price_list_switching) or not created at all
# (allow_warehouse_change), so they silently go missing on DB restores or when
# a patch is skipped. Re-asserting them here (idempotently) on every migrate
# makes them self-heal.
CREDIT_SALES_DESCRIPTION = (
    "Lets cashiers sell on credit: an unpaid invoice with a due date, for a named customer. "
    "Credit sales are booked as POS sales and count in the till's shift."
)

DAILY_CLOSE_DESCRIPTION = (
    "On (default): a shift is good for the day it was opened. The next day the till cannot "
    "sell until that shift is closed. Off: a shift stays good until someone closes it, so "
    "closing is when the money is counted, not a daily chore. Turning it back on while a "
    "shift from an earlier day is open stops sales on the till until that shift is closed."
)

ALLOW_CLOSING_DESCRIPTION = (
    "On (default): this till's users close its shift from the Closing Shift screen. Off: "
    "they do not see that screen or its figures, and cannot close the shift from the till or "
    "the desk; a manager (Sales Manager, System Manager, Express Admin) joins the shift and "
    "closes it - for that, the manager is listed under this till's Applicable for Users and "
    "has no open shift of their own."
)

POS_PROFILE_FEATURE_FIELDS = [
    {
        "fieldname": "allow_price_list_switching",
        "label": "Allow Price List Switching",
        "fieldtype": "Check",
        "insert_after": "allow_zero_rate_sales",
        "description": "Allow cashiers to switch selling price lists in Klik POS.",
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "allow_warehouse_change",
        "label": "Allow Warehouse Change",
        "fieldtype": "Check",
        "insert_after": "allow_price_list_switching",
        "description": "Allow cashiers to switch the selling warehouse in Klik POS.",
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_enable_sales_lens",
        "label": "Show Customer Sales Lens",
        "fieldtype": "Check",
        "insert_after": "allow_warehouse_change",
        "description": "Show a customer purchase-history snapshot tab in the POS item details modal.",
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_show_overdue_warning",
        "label": "Show Overdue Invoice Warning",
        "fieldtype": "Check",
        "insert_after": "custom_enable_sales_lens",
        "description": "Show a warning popup when selecting a customer with overdue invoices in the POS.",
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_allow_credit_sales_as_pos",
        "label": "Allow Credit Sales",
        "fieldtype": "Check",
        "insert_after": "custom_show_overdue_warning",
        "description": CREDIT_SALES_DESCRIPTION,
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_allow_viewing_other_cashiers",
        "label": "Allow Viewing Other Cashiers' Invoices",
        "fieldtype": "Check",
        "insert_after": "custom_allow_credit_sales_as_pos",
        "description": (
            "Invoice History only. When off (default), every user on this profile sees "
            "only the invoices they rang, and the cashier filter is locked to their own "
            "name. When on, anyone on this till may filter by and read any cashier's "
            "invoices. This is a property of the till, not of the person: it applies to "
            "managers too. The Sales Dashboard is unaffected - it never restricts data, "
            "and is instead limited to who may open it."
        ),
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_enable_shipping_rule",
        "label": "Enable Shipping Rule at Checkout",
        "fieldtype": "Check",
        "insert_after": "custom_allow_viewing_other_cashiers",
        "description": (
            "Let cashiers pick a Selling Shipping Rule at checkout. The rule's charge is added "
            "as its own row on the invoice, and the Delivery Charge box is disabled while a "
            "rule is chosen."
        ),
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_use_item_code_as_display_name",
        "label": "Show Item Code Instead Of Item Name",
        "fieldtype": "Check",
        "insert_after": "custom_enable_shipping_rule",
        "description": (
            "Replace the item name with the item code as the primary label in the item list, "
            "cart, and checkout preview. Different from the 'Show Item Code' checkbox (POS "
            "Configurations tab), which adds the code as a secondary line alongside the name "
            "rather than replacing it - turning both on shows the code as the primary label "
            "and the name as the secondary line. The printed receipt is unaffected either way; "
            "it comes from the selected Print Format, not this display."
        ),
        "default": "0",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_require_daily_shift_close",
        "label": "Require Daily Shift Close",
        "fieldtype": "Check",
        "insert_after": "custom_clear_draft_invoices",
        "description": DAILY_CLOSE_DESCRIPTION,
        "default": "1",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_allow_closing_shift",
        "label": "Allow Closing Shift",
        "fieldtype": "Check",
        "insert_after": "custom_require_daily_shift_close",
        "description": ALLOW_CLOSING_DESCRIPTION,
        "default": "1",
        "module": "KLiK PoS",
    },
    {
        "fieldname": "custom_enable_loss_of_sale",
        "label": "Record Loss of Sale",
        "fieldtype": "Check",
        "insert_after": "custom_use_item_code_as_display_name",
        "description": (
            "When a cashier asks for more than is in stock, sell what is in stock and record "
            "the rest on the invoice line as LoS Qty (Loss of Sale) instead of refusing the line."
        ),
        "default": "0",
        "module": "KLiK PoS",
    },
]


def install_pos_profile_feature_fields():
    """Idempotent and collision-safe. Only creates feature fields the POS Profile
    doctype does not already have (as a STANDARD or custom field) — some stacks
    ship `allow_warehouse_change` as a standard field, and creating a Custom Field
    with a colliding name raises. Returns the list of fieldnames actually created.
    Safe to run on every migrate."""
    missing = [f for f in POS_PROFILE_FEATURE_FIELDS if not _field_is_defined(f["fieldname"])]
    if missing:
        create_custom_fields({"POS Profile": missing}, update=True)
    return [f["fieldname"] for f in missing]


def _field_is_defined(fieldname):
    """True when POS Profile defines the field, as a standard DocField or a Custom
    Field record. Not a column check: deleting a Custom Field leaves its column
    behind, and a column-only check would then never recreate the field, so the
    checkbox stays missing from the form for good."""
    return bool(
        frappe.db.exists("DocField", {"parent": "POS Profile", "fieldname": fieldname})
        or frappe.db.exists("Custom Field", {"dt": "POS Profile", "fieldname": fieldname})
    )


def install_pos_extra_fields_child():
    """Create the `POS Extra Field` child doctype and the `custom_pos_extra_fields`
    Table custom field on POS Profile. Idempotent and safe on every migrate."""
    if not frappe.db.exists("DocType", "POS Extra Field"):
        child = frappe.new_doc("DocType")
        child.update({
            "name": "POS Extra Field",
            "module": "KLiK PoS",
            "custom": 1,
            "istable": 1,
            "fields": [
                {
                    "fieldname": "so_si_commonfield",
                    "label": "SO/SI Common Field",
                    # Autocomplete, not Select: the candidates are whatever Sales Order and
                    # Sales Invoice have in common ON THIS SITE, so they cannot be baked into
                    # a static options list. public/js/pos_profile.js fills them in from
                    # get_pos_extra_field_candidates, as {label, value} pairs - the control
                    # shows the label and stores the fieldname, which is what the server
                    # intersects on in get_configured_extra_fieldnames.
                    "fieldtype": "Autocomplete",
                    "description": "Common field in Sales Order / Sales Invoice",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "reqd",
                    "label": "Required",
                    "fieldtype": "Check",
                    "in_list_view": 1,
                    "default": "0",
                },
            ],
            "permissions": [],
        })
        child.insert(ignore_permissions=True)

    _ensure_extra_field_picker()

    # Column break so the extra-fields table sits in its own column (more width),
    # within the same section as the price-list / warehouse toggles.
    if not frappe.db.exists("Custom Field", {"dt": "POS Profile", "fieldname": "custom_pos_extra_fields_cb"}):
        create_custom_fields({
            "POS Profile": [{
                "fieldname": "custom_pos_extra_fields_cb",
                "label": "",
                "fieldtype": "Column Break",
                "insert_after": "allow_warehouse_change",
                "module": "KLiK PoS",
            }]
        }, update=True)

    if not frappe.db.exists("Custom Field", {"dt": "POS Profile", "fieldname": "custom_pos_extra_fields"}):
        create_custom_fields({
            "POS Profile": [{
                "fieldname": "custom_pos_extra_fields",
                "label": "POS Extra Fields",
                "fieldtype": "Table",
                "options": "POS Extra Field",
                "insert_after": "custom_pos_extra_fields_cb",
                "description": "Extra SO/SI common fields to capture in the POS Additional Info dialog.",
                "module": "KLiK PoS",
            }]
        }, update=True)


def _ensure_extra_field_picker():
    """Upgrade `so_si_commonfield` from the Select it shipped as to an Autocomplete.

    install_pos_extra_fields_child() only creates the child doctype when it is missing,
    so every site that already had it kept the original Select - which carried no
    `options` and so rendered an empty, unpickable, required dropdown. Runs on every
    migrate and writes only when something actually differs.
    """
    if not frappe.db.exists("DocType", "POS Extra Field"):
        return

    doc = frappe.get_doc("DocType", "POS Extra Field")
    changed = False
    for row in doc.fields:
        if row.fieldname != "so_si_commonfield":
            continue
        if row.fieldtype != "Autocomplete":
            row.fieldtype = "Autocomplete"
            changed = True
        # A leftover Select options blob would be offered verbatim as candidates.
        if row.options:
            row.options = None
            changed = True

    if changed:
        doc.save(ignore_permissions=True)


def ensure_pos_extra_fields_child():
    """Hook-safe wrapper. Never abort migrate on failure."""
    try:
        install_pos_extra_fields_child()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: POS Extra Field child install failed")


def install_mpesa_reconciled_payment_child():
    """Create the `POS Mpesa Reconciled Payment` child doctype and the
    `custom_mpesa_reconciled_payments` Table custom field on Sales Invoice.
    Idempotent and safe on every migrate.

    Traceability-only record of which `Mpesa C2B Payment Register` row(s)
    were reconciled onto a given Sales Invoice via the POS "Add Selected
    Payments" flow (`klik_pos.api.mpesa.process_mpesa`).
    `mpesa_c2b_payment_register` is stored as plain Data (not a Link) so this
    child table has zero schema dependency on the `frappe_mpsa_payments` app
    being installed/reachable at display time.
    """
    if not frappe.db.exists("DocType", "POS Mpesa Reconciled Payment"):
        child = frappe.new_doc("DocType")
        child.update({
            "name": "POS Mpesa Reconciled Payment",
            "module": "KLiK PoS",
            "custom": 1,
            "istable": 1,
            "fields": [
                {
                    "fieldname": "mpesa_c2b_payment_register",
                    "label": "Mpesa C2B Payment Register",
                    "fieldtype": "Data",
                    "description": "Name of the reconciled Mpesa C2B Payment Register row (plain text, not a Link).",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "transid",
                    "label": "Transaction ID",
                    "fieldtype": "Data",
                    "in_list_view": 1,
                },
                {
                    "fieldname": "amount",
                    "label": "Amount",
                    "fieldtype": "Currency",
                    "in_list_view": 1,
                },
                {
                    "fieldname": "msisdn",
                    "label": "Phone Number",
                    "fieldtype": "Data",
                    "in_list_view": 1,
                },
                {
                    "fieldname": "mode_of_payment",
                    "label": "Mode of Payment",
                    "fieldtype": "Link",
                    "options": "Mode of Payment",
                    "in_list_view": 1,
                },
                {
                    "fieldname": "excess_payment_entry",
                    "label": "Excess Payment Entry",
                    "fieldtype": "Data",
                    "description": "Name of the unallocated Payment Entry holding this receipt's overpaid excess as reusable customer credit (plain text, not a Link).",
                    "read_only": 1,
                },
                {
                    "fieldname": "payment_entry",
                    "label": "Payment Entry",
                    "fieldtype": "Data",
                    "description": "The Payment Entry created for this receipt's full amount (plain text, not a Link).",
                    "read_only": 1,
                    "in_list_view": 1,
                },
                {
                    "fieldname": "allocated_amount",
                    "label": "Allocated to this Invoice",
                    "fieldtype": "Currency",
                    "description": "How much of the receipt's Payment Entry this invoice took as an advance. The rest stays unallocated on that entry.",
                    "read_only": 1,
                    "in_list_view": 1,
                },
            ],
            "permissions": [],
        })
        child.insert(ignore_permissions=True)
    else:
        child = frappe.get_doc("DocType", "POS Mpesa Reconciled Payment")
        _missing_child_fields = [
            {
                "fieldname": "mode_of_payment",
                "label": "Mode of Payment",
                "fieldtype": "Link",
                "options": "Mode of Payment",
                "in_list_view": 1,
            },
            {
                "fieldname": "excess_payment_entry",
                "label": "Excess Payment Entry",
                "fieldtype": "Data",
                "description": "Name of the unallocated Payment Entry holding this receipt's overpaid excess as reusable customer credit (plain text, not a Link).",
                "read_only": 1,
            },
            {
                "fieldname": "payment_entry",
                "label": "Payment Entry",
                "fieldtype": "Data",
                "description": "The Payment Entry created for this receipt's full amount (plain text, not a Link).",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "allocated_amount",
                "label": "Allocated to this Invoice",
                "fieldtype": "Currency",
                "description": "How much of the receipt's Payment Entry this invoice took as an advance. The rest stays unallocated on that entry.",
                "read_only": 1,
                "in_list_view": 1,
            },
        ]
        existing = {f.fieldname for f in child.fields}
        appended = False
        for field_def in _missing_child_fields:
            if field_def["fieldname"] not in existing:
                child.append("fields", field_def)
                appended = True
        if appended:
            child.save(ignore_permissions=True)

    if not frappe.db.exists(
        "Custom Field", {"dt": "Sales Invoice", "fieldname": "custom_mpesa_reconciled_payments"}
    ):
        create_custom_fields({
            "Sales Invoice": [{
                "fieldname": "custom_mpesa_reconciled_payments",
                "label": "Mpesa Reconciled Payments",
                "fieldtype": "Table",
                "options": "POS Mpesa Reconciled Payment",
                "insert_after": "payments",
                "description": "Mpesa C2B Payment Register rows reconciled onto this invoice via the POS M-Pesa Payment Options flow.",
                "module": "KLiK PoS",
                "read_only": 1,
            }]
        }, update=True)


def ensure_mpesa_reconciled_payment_child():
    """Hook-safe wrapper. Never abort migrate on failure."""
    try:
        install_mpesa_reconciled_payment_child()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: POS Mpesa Reconciled Payment child install failed")


def install_pos_closing_entry_invoice_table():
    """Create the `custom_sales_invoice` Table field on POS Closing Entry.

    _populate_sales_invoices_to_closing_entry (api/pos_entry.py) has always appended to this
    field, but nothing ever created it: klik_pos ships only Property Setter fixtures, and the
    `Klik Sales Invoice Reference` child doctype it targets was added without the field that
    would hold it. The append therefore raised AttributeError on every shift close, was
    swallowed by the surrounding try/except so the closing entry still saved, and left an
    Error Log row nobody read - so the invoice breakdown has never appeared on a closing
    entry on any site.

    Read-only: it is a traceability record of what the shift sold, rebuilt from the invoices
    themselves, not something to hand-edit.
    """
    if not frappe.db.exists("DocType", "Klik Sales Invoice Reference"):
        # Shipped with the app; if it is missing the field would point at nothing.
        return

    if not frappe.db.exists(
        "Custom Field", {"dt": "POS Closing Entry", "fieldname": "custom_sales_invoice"}
    ):
        create_custom_fields({
            "POS Closing Entry": [{
                "fieldname": "custom_sales_invoice",
                "label": "Sales Invoices",
                "fieldtype": "Table",
                "options": "Klik Sales Invoice Reference",
                "insert_after": "pos_transactions",
                "description": "Sales Invoices submitted against this shift's POS Opening Entry.",
                "module": "KLiK PoS",
                "read_only": 1,
            }]
        }, update=True)


def ensure_pos_closing_entry_invoice_table():
    """Hook-safe wrapper. Never abort migrate on failure."""
    try:
        install_pos_closing_entry_invoice_table()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(), "klik_pos: POS Closing Entry invoice table install failed"
        )


def install_opening_entry_variance_fields():
    """Two columns on the opening's balance rows: what the till last closed at, and why
    today's figure differs. Both are read by klik_pos.api.opening_balances, which refuses
    an unexplained change; the guard degrades to silence if these are ever absent."""
    fields = [
        {
            "fieldname": "custom_previous_closing_amount",
            "label": "Left In Drawer At Last Closing",
            "fieldtype": "Currency",
            "read_only": 1,
            "insert_after": "opening_amount",
            "description": "What this till's last closing counted, less what was handed over for banking. Zero for a mode that holds no float.",
            "module": "KLiK PoS",
        },
        {
            "fieldname": "custom_variance_reason",
            "label": "Reason For Difference",
            "fieldtype": "Small Text",
            "insert_after": "custom_previous_closing_amount",
            "description": "Required when the opening amount differs from what this till last closed at.",
            "module": "KLiK PoS",
        },
    ]
    missing = [
        f for f in fields if not frappe.db.has_column("POS Opening Entry Detail", f["fieldname"])
    ]
    if missing:
        create_custom_fields({"POS Opening Entry Detail": missing}, update=True)

    # The cash handed over for banking at closing. The next opening is suggested at the
    # count less this, rather than at the whole count.
    banked = {
        "fieldname": "custom_banked_amount",
        "label": "Handed Over For Banking",
        "fieldtype": "Currency",
        "insert_after": "closing_amount",
        "description": "Cash taken out of the drawer at closing to be banked. The next opening "
        "on this till is suggested at the count less this. Cash-type modes only.",
        "module": "KLiK PoS",
    }
    if not frappe.db.has_column("POS Closing Entry Detail", banked["fieldname"]):
        create_custom_fields({"POS Closing Entry Detail": [banked]}, update=True)
        missing.append(banked)
    # What the opening row records is now the float left after banking, not the raw count.
    frappe.db.set_value(
        "Custom Field",
        {"dt": "POS Opening Entry Detail", "fieldname": "custom_previous_closing_amount"},
        {
            "label": "Left In Drawer At Last Closing",
            "description": "What this till's last closing counted, less what was handed over "
            "for banking. Zero for a mode that holds no float.",
        },
    )
    return [f["fieldname"] for f in missing]


def ensure_opening_entry_variance_fields():
    """Hook entrypoint. Never abort a migrate over a reporting column."""
    try:
        install_opening_entry_variance_fields()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: opening variance field install failed")


def install_sales_order_remarks():
    """Give Sales Order a Remarks field, as Sales Invoice has, so a held order's note survives
    to the invoice. Only where the site has none - a standard or custom `remarks` is kept.
    Placed in More Info, by the status, as on Sales Invoice. Returns True when created."""
    ours = frappe.db.get_value(
        "Custom Field", {"dt": "Sales Order", "fieldname": "remarks", "module": "KLiK PoS"}, "name"
    )
    if frappe.db.exists("DocField", {"parent": "Sales Order", "fieldname": "remarks"}):
        # ERPNext has its own now: ours would show the field twice.
        if ours:
            frappe.delete_doc("Custom Field", ours, ignore_permissions=True)
        return False
    if ours:
        # Like Sales Invoice's, a cashier's note stays off printed orders.
        frappe.db.set_value("Custom Field", ours, "print_hide", 1)
        return False
    if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": "remarks"}):
        return False
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": "remarks",
                    "label": "Remarks",
                    "fieldtype": "Small Text",
                    "insert_after": "advance_payment_status",
                    "print_hide": 1,
                    "module": "KLiK PoS",
                }
            ]
        },
        update=True,
    )
    return True


def ensure_sales_order_remarks():
    try:
        install_sales_order_remarks()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: Sales Order remarks field install failed")


LOS_QTY_FIELD = {
    "fieldname": "custom_los_qty",
    "label": "LoS Qty",
    "fieldtype": "Float",
    "insert_after": "qty",
    "read_only": 1,
    "in_list_view": 1,
    "columns": 1,
    "no_copy": 1,
    "print_hide": 1,
    "description": "Asked for but not in stock: recorded as Loss of Sale.",
    "module": "KLiK PoS",
}


def install_los_qty_field():
    """LoS Qty on Sales Invoice Item. Returns True when created."""
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice Item", "fieldname": LOS_QTY_FIELD["fieldname"]}):
        return False
    create_custom_fields({"Sales Invoice Item": [LOS_QTY_FIELD]}, update=True)
    return True


def ensure_los_qty_field():
    try:
        install_los_qty_field()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: LoS Qty field install failed")


def ensure_pos_profile_feature_fields():
    """Hook entrypoint for after_migrate / after_install. Never abort on failure."""
    try:
        install_pos_profile_feature_fields()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: POS Profile feature-field install failed")
    ensure_pos_extra_fields_child()
    ensure_mpesa_reconciled_payment_child()
    ensure_pos_closing_entry_invoice_table()
    ensure_opening_entry_variance_fields()
    ensure_sales_order_remarks()
    ensure_los_qty_field()
