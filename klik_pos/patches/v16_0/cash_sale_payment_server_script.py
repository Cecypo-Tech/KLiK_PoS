import frappe

NAME = "Sales Invoice - Cash Requires Payment"

# A desk rule, so it ships as a Server Script a site turns on (Setup > Server Script) only
# if it wants it. Till sales (custom_is_created_from_klik) are left to the till.
SCRIPT = """# A Cash sale made on the desk is fully paid by the time it is submitted - on the
# invoice itself or by advances. Credit sales carry the balance as outstanding.
# Till sales are skipped. Only real desk/API submissions are checked:
# frappe.request.path is blank for bench scripts, tests and background jobs.
if (
    doc.get("custom_sale_type") == "Cash"
    and not doc.get("custom_is_created_from_klik")
    and not doc.is_return
    and not doc.get("is_consolidated")
    and frappe.request.path
    and frappe.utils.flt(doc.outstanding_amount, 2) > 0
):
    frappe.throw(
        "Cash Sales require full payment before submission. Receive the payment, "
        "or make this a Credit sale."
    )
"""


def execute():
	"""Ship the Cash-sale payment check disabled. A site that already has a script by this
	name (Allparts wrote the original) keeps its own."""
	if frappe.db.exists("Server Script", NAME):
		return
	frappe.get_doc(
		{
			"doctype": "Server Script",
			"__newname": NAME,
			"script_type": "DocType Event",
			"reference_doctype": "Sales Invoice",
			"doctype_event": "Before Submit",
			"module": "KLiK PoS",
			"disabled": 1,
			"script": SCRIPT,
		}
	).insert(ignore_permissions=True)
