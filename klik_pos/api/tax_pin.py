"""KRA PIN lookup for the till, through cecypo_pin_checker when that app is installed.

klik_pos must work without it, so nothing here imports the app at module level: availability
is decided at runtime, and every failure comes back as a message rather than an exception the
cashier would see as a broken dialog.
"""

import re

import frappe
from frappe import _

PIN_CHECKER_APP = "cecypo_pin_checker"
PIN_PATTERN = re.compile(r"^[A-Z]\d{9}[A-Z]$")
KRA_OK = "23000"


def pin_checker_available():
	"""Installed on this site and configured well enough to call the KRA API."""
	if PIN_CHECKER_APP not in frappe.get_installed_apps():
		return False
	try:
		settings = frappe.get_cached_doc("PIN Checker Settings")
	except Exception:
		return False
	return bool(settings.get("api_url") and settings.get("api_key") and settings.get("api_secret"))


@frappe.whitelist()
def lookup_tax_pin(pin=None):
	"""Resolve a KRA PIN to the registered taxpayer name.

	Returns {available, success, name, status, message}. `name` is only set for an Active PIN,
	which is also when cecypo_pin_checker itself fills a name in.
	"""
	pin = (pin or "").strip().upper()
	result = {"available": pin_checker_available(), "success": False, "name": "", "status": "", "message": ""}

	if not result["available"]:
		result["message"] = _("PIN lookup is not available on this site.")
		return result

	if not PIN_PATTERN.match(pin):
		result["message"] = _("Enter a PIN like P051189348K to look it up.")
		return result

	try:
		validate_pin = frappe.get_attr(f"{PIN_CHECKER_APP}.{PIN_CHECKER_APP}.api.validate_pin")
		response = validate_pin(pin) or {}
	except Exception:
		frappe.clear_last_message()
		result["message"] = _("Could not reach the KRA PIN checker. Try again.")
		return result

	pin_data = response.get("PINDATA") if isinstance(response, dict) else None
	if response.get("ResponseCode") != KRA_OK or not pin_data:
		result["message"] = _("No taxpayer found for {0}.").format(pin)
		return result

	status = (pin_data.get("StatusOfPIN") or "").strip()
	result["status"] = status
	if status != "Active":
		result["message"] = _("PIN {0} is {1}.").format(pin, status or _("not active"))
		return result

	name = (pin_data.get("Name") or "").strip()
	# The KRA API pads individual names with empty middle/last parts.
	if name.endswith(" NA NA"):
		name = name[:-6].strip()

	result.update({"success": bool(name), "name": name})
	if not name:
		result["message"] = _("PIN {0} is active but has no registered name.").format(pin)
	return result
