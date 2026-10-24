import frappe
from werkzeug.routing import RequestRedirect

POS_ONLY_ROLE = "KLiK Only"


def before_request():
	"""Staff with the KLiK Only role sell from the POS and never reach the desk."""
	path = frappe.request.path
	if any(path == p or path.startswith(p + "/") for p in ("/desk", "/app")) and POS_ONLY_ROLE in frappe.get_roles():
		raise RequestRedirect("/klik_pos")
