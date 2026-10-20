# Test package for klik_pos
import frappe


def mute_workflow_emails():
	"""No workflow action emails for the whole run.

	An active Sales Order workflow with email alerts (PowerPack's price approval) mails the
	approvers on every save a test makes - inline under frappe.in_test, with a PDF of the
	order, so each save starts headless Chromium. Mid-run that failed held-order and tax
	tests and finally killed the runner. Frappe mutes the mail itself in tests, but only
	after the PDF is built. The site's workflow stays as it is.
	"""
	from frappe.workflow.doctype.workflow_action import workflow_action

	# Assigned, not patch().start(): a test's patch.stopall (test_queue_lock_retry) stops
	# every started patcher, and took this one with it mid-run.
	workflow_action.send_workflow_action_email = lambda doc, transitions: None


# On import, not as a before_tests hook: Frappe runs that hook only for suites it files as
# FrappeTestCase/IntegrationTestCase by their direct base, so a module whose classes share a
# base of their own (test_warehouse_visibility's Tills) ran alone without it. Every test
# module imports this package. QA scripts that borrow its fixtures run outside tests and
# keep their emails.
if frappe.in_test:
	mute_workflow_emails()
