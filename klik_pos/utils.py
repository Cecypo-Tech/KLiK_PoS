import frappe
from werkzeug.routing import RequestRedirect

POS_ONLY_ROLE = "KLiK Only"


def before_request():
	"""Staff with the KLiK Only role sell from the POS and never reach the desk."""
	path = frappe.request.path
	if not any(path == p or path.startswith(p + "/") for p in ("/desk", "/app")):
		return
	# Administrator is handed every role on the site, this one included.
	if frappe.session.user == "Administrator" or POS_ONLY_ROLE not in frappe.get_roles():
		return
	redirect = RequestRedirect("/klik_pos")
	redirect.code = 302  # 308 is cached by the browser for good, even after the role is removed
	raise redirect


def ensure_pos_only_role():
	"""Create the role once. Never update it: a site may disable or change it, and migrate must keep that."""
	if not frappe.db.exists("Role", POS_ONLY_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": POS_ONLY_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
