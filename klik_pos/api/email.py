import json
import re

import frappe
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.utils import fmt_money, now

from klik_pos.klik_pos.utils import error_reason, get_current_pos_profile


def render_email(doc, template=None, message=None, fallback_subject="", fallback_message=""):
	"""(subject, message) for emailing `doc`. The Email Template gives the subject and, unless the
	cashier's own `message` is passed, the body. Both are Jinja-rendered with `doc`; text that
	isn't valid Jinja is sent as typed."""
	d = doc.as_dict()
	name = d.get("customer_name") or ""
	total = frappe.utils.fmt_money(d.get("rounded_total") or d.get("grand_total") or 0, currency=d.get("currency"))
	# The checkout's older {{placeholder}} names, filled from the document. Delivery ones have no
	# source on an invoice and go blank.
	aliases = {
		"customer": name, "first_name": name.split(" ")[0], "last_name": " ".join(name.split(" ")[1:]),
		"address": d.get("address_display") or "", "customer_address": d.get("address_display") or "",
		"invoice_number": doc.name, "delivery_note": doc.name, "invoice_total": total, "grand_total": total,
		"company_name": d.get("company") or "",
		"date": frappe.utils.formatdate(d.get("posting_date") or d.get("transaction_date")),
		"departure_time": "", "estimated_arrival": "", "driver_name": "", "cell_number": "", "vehicle": "",
	}
	ctx = {**d, **aliases, "doc": d}

	def render(text):
		try:
			return frappe.render_template(text, ctx)
		except Exception:
			return text

	t = frappe.get_doc("Email Template", template) if template else None
	subject = render(t.subject) if t and t.subject else fallback_subject
	if message:
		body = render(message)
	elif t:
		body = render((t.response_html if t.use_html else t.response) or "")
	else:
		body = fallback_message
	# Plain text in an HTML email loses its line breaks; keep them. HTML is left as written.
	if not re.search(r"</?[a-zA-Z][^>]*>", body):
		body = frappe.utils.escape_html(body).replace("\n", "<br>")
	return subject, body


def _invoice_email(doc, data, pos_profile):
	"""(subject, message) for the checkout's invoice email; shared by send and preview."""
	amount = fmt_money(doc.rounded_total or doc.grand_total, currency=doc.currency)
	return render_email(
		doc,
		template=data.get("template") or pos_profile.get("custom_email_template"),
		message=data.get("message"),
		fallback_subject=f"Invoice {doc.name} from {doc.company}",
		fallback_message=(
			f"<p>Dear {data.get('customer_name') or doc.customer_name},</p>"
			f"<p>Please find attached your invoice <b>{doc.name}</b>.</p>"
			f"<p>The total amount due is <b>{amount}</b>.</p>"
			"<p>Thank you for your business.</p>"
		),
	)


@frappe.whitelist()
def preview_invoice_email(**data):
	"""The subject and body send_invoice_email would send, for the checkout's preview."""
	doc = frappe.get_doc("Sales Invoice", data.get("invoice_data"))
	doc.check_permission("read")
	subject, message = _invoice_email(doc, data, get_current_pos_profile())
	return {"subject": subject, "message": message}


@frappe.whitelist()
def send_invoice_email(**kwargs):
	"""
	Accepts frontend payload and sends invoice email with PDF attachment.
	"""
	data = kwargs

	email = data.get("email")
	customer_name = data.get("customer_name")
	invoice_no = data.get("invoice_data")
	sender = data.get("sender")

	if not (email and invoice_no):
		frappe.throw("Email and invoice number are required.")

	try:
		doc = frappe.get_doc("Sales Invoice", invoice_no)

		pos_profile = get_current_pos_profile()
		print_format = pos_profile.print_format or pos_profile.print_format or "Standard"

		pdf_data = frappe.get_print("Sales Invoice", doc.name, print_format=print_format, as_pdf=True)

		invoice_amount = fmt_money(doc.rounded_total or doc.grand_total, currency=doc.currency)

		subject, message = _invoice_email(doc, data, pos_profile)

		attachments = [{"fname": f"{doc.name}.pdf", "fcontent": pdf_data}]

		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=message,
			attachments=attachments,
			delayed=False,
			sender=sender,
		)

		return {
			"status": "success",
			"recipients": [email],
			"invoice": invoice_no,
			"amount": invoice_amount,
			"print_format": print_format,
			"timestamp": now(),
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Send Invoice Email Failed")
		frappe.throw(f"Failed to send invoice email: {error_reason(e)}")


@frappe.whitelist()
def get_email_templates():
	"""
	Get all Email templates
	"""
	try:
		templates = frappe.get_all(
			"Email Template",
			filters={},
			fields=["name", "subject", "response_html", "response"],
		)
		return templates
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Email Templates Failed")
		frappe.throw(f"Failed to get Email templates: {error_reason(e)}")


@frappe.whitelist()
def get_email_template(template_name):
    """
    Get a specific Email template by name
    """
    try:
        template = frappe.get_doc("Email Template", template_name)
        return {
            "name": template.name,
            "subject": template.subject,
            "response_html": template.response_html,
            "response": template.response,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Email Template Failed")
        frappe.throw(f"Failed to get Email template: {error_reason(e)}")


def _format_account(doc: EmailAccount, source: str) -> dict:
    return {
        "name": getattr(doc, "name", None),
        "email_id": getattr(doc, "email_id", None),
        "default_sender": getattr(doc, "default_sender", None),
        "source": source,
        "is_exists_in_db": bool(getattr(doc, "is_exists_in_db", lambda: False)()),
    }


@frappe.whitelist()
def get_available_outgoing_accounts(
    user: str | None = None, company: str | None = None
) -> list[dict]:
    """
    Get a list of email accounts that can be used to send emails.

    Order of selection:
    1. Accounts linked to the user's email.
    2. The system's default outgoing account.
    3. Account set in site configuration.

    Returns a list of accounts with basic details.
    """

    accounts: list[dict] = []
    seen = set()

    user = user or frappe.session.user

    if user:
        user_emails = frappe.get_all(
            "User Email",
            filters={"parent": user, "enable_outgoing": 1},
            fields=["email_account", "email_id", "awaiting_password", "used_oauth"],
        )

        for ue in user_emails:
            email_account_name = ue.get("email_account")
            if not email_account_name or email_account_name in seen:
                continue
            try:
                doc = frappe.get_doc("Email Account", email_account_name)
            except Exception:
                continue

            entry = _format_account(doc, "user_email")
            entry.update(
                {
                    "user_email_id": ue.get("email_id"),
                    "awaiting_password": bool(ue.get("awaiting_password")),
                    "used_oauth": bool(ue.get("used_oauth")),
                }
            )
            accounts.append(entry)
            seen.add(email_account_name)

    # default outgoing
    try:
        default_doc = EmailAccount.find_default_outgoing()
    except Exception:
        default_doc = None

    if default_doc:
        if isinstance(default_doc, dict):
            default_doc = next(iter(default_doc.values()))
        if getattr(default_doc, "name", None) and default_doc.name not in seen:
            accounts.append(_format_account(default_doc, "default_outgoing"))
            seen.add(default_doc.name)

    # site config (explicit)
    try:
        site_doc = EmailAccount.find_from_config()
    except Exception:
        site_doc = None

    if site_doc:
        name = getattr(site_doc, "name", None)
        if name and name not in seen:
            accounts.append(_format_account(site_doc, "site_config"))
            seen.add(name)

    return {
        "status": "success",
        "accounts": accounts,
    }


@frappe.whitelist()
def ensure_outgoing_configured(
    user: str | None = None, company: str | None = None
) -> bool:
    """Return True if at least one outgoing Email Account candidate exists.

    Use this before sending an invoice to prompt the user to configure/select an account.
    """
    accounts = get_available_outgoing_accounts(user=user, company=company)
    return bool(accounts)
