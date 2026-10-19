# Test package for klik_pos

from unittest.mock import patch


def mute_workflow_emails():
	"""before_tests: no workflow action emails for the whole run.

	An active Sales Order workflow with email alerts (PowerPack's price approval) mails the
	approvers on every save a test makes - inline under frappe.in_test, with a PDF of the
	order, so each save starts headless Chromium. Mid-run that failed held-order and tax
	tests and finally killed the runner. Frappe mutes the mail itself in tests, but only
	after the PDF is built. The site's workflow stays as it is.
	"""
	target = "frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email"
	if not getattr(mute_workflow_emails, "patcher", None):
		mute_workflow_emails.patcher = patch(target, new=lambda doc, transitions: None)
		mute_workflow_emails.patcher.start()
