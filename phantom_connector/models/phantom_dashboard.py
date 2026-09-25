from datetime import timedelta

from odoo import _, api, fields, models


class PhantomDashboard(models.AbstractModel):
    """Backend data provider for the Phantom dashboard client action
    (phantom_connector/static/src/components/phantom_dashboard). Every
    method here is meant to be called via RPC from that OWL component.
    """

    _name = "phantom.dashboard"
    _description = "Phantom Dashboard"
    _inherit = "dashboards.drilldown.mixin"

    @api.model
    def get_dashboard_data(self):
        company = self.env.company
        invoice_model = self.env["phantom.invoice"]
        receipt_model = self.env["phantom.receipt"]

        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        prev_month_end = month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        this_month_domain = [
            ("company_id", "=", company.id),
            ("invoice_date", ">=", month_start),
            ("invoice_date", "<=", today),
        ]
        last_month_domain = [
            ("company_id", "=", company.id),
            ("invoice_date", ">=", prev_month_start),
            ("invoice_date", "<=", prev_month_end),
        ]
        receipt_this_month_domain = [
            ("company_id", "=", company.id),
            ("receipt_date", ">=", month_start),
            ("receipt_date", "<=", today),
        ]
        receipt_last_month_domain = [
            ("company_id", "=", company.id),
            ("receipt_date", ">=", prev_month_start),
            ("receipt_date", "<=", prev_month_end),
        ]
        pending_invoice_domain = [("company_id", "=", company.id), ("state", "=", "pending")]
        pending_receipt_domain = [("company_id", "=", company.id), ("state", "=", "pending")]
        error_invoice_domain = [("company_id", "=", company.id), ("state", "=", "error")]
        error_receipt_domain = [("company_id", "=", company.id), ("state", "=", "error")]

        this_month_rows = invoice_model._read_group(this_month_domain, [], ["amount_total:sum"])
        last_month_rows = invoice_model._read_group(last_month_domain, [], ["amount_total:sum"])
        receipt_this_month_rows = receipt_model._read_group(
            receipt_this_month_domain, [], ["amount_total:sum"]
        )
        receipt_last_month_rows = receipt_model._read_group(
            receipt_last_month_domain, [], ["amount_total:sum"]
        )

        return {
            "currency_id": company.currency_id.id,
            "invoices_this_month_count": invoice_model.search_count(this_month_domain),
            "invoices_this_month_amount": this_month_rows[0][0] if this_month_rows else 0.0,
            "invoices_this_month_drilldown": self._get_drilldown_action(
                "phantom.invoice", domain=this_month_domain, name=_("Invoices this month"),
            ),
            "invoices_last_month_count": invoice_model.search_count(last_month_domain),
            "invoices_last_month_amount": last_month_rows[0][0] if last_month_rows else 0.0,
            "invoices_last_month_drilldown": self._get_drilldown_action(
                "phantom.invoice", domain=last_month_domain, name=_("Invoices last month"),
            ),
            "receipts_this_month_count": receipt_model.search_count(receipt_this_month_domain),
            "receipts_this_month_amount": (
                receipt_this_month_rows[0][0] if receipt_this_month_rows else 0.0
            ),
            "receipts_this_month_drilldown": self._get_drilldown_action(
                "phantom.receipt", domain=receipt_this_month_domain, name=_("Receipts this month"),
            ),
            "receipts_last_month_count": receipt_model.search_count(receipt_last_month_domain),
            "receipts_last_month_amount": (
                receipt_last_month_rows[0][0] if receipt_last_month_rows else 0.0
            ),
            "receipts_last_month_drilldown": self._get_drilldown_action(
                "phantom.receipt", domain=receipt_last_month_domain, name=_("Receipts last month"),
            ),
            "invoices_pending_count": invoice_model.search_count(pending_invoice_domain),
            "invoices_pending_drilldown": self._get_drilldown_action(
                "phantom.invoice", domain=pending_invoice_domain, name=_("Pending Invoices"),
            ),
            "receipts_pending_count": receipt_model.search_count(pending_receipt_domain),
            "receipts_pending_drilldown": self._get_drilldown_action(
                "phantom.receipt", domain=pending_receipt_domain, name=_("Pending Receipts"),
            ),
            "invoices_error_count": invoice_model.search_count(error_invoice_domain),
            "invoices_error_drilldown": self._get_drilldown_action(
                "phantom.invoice", domain=error_invoice_domain, name=_("Invoices with errors"),
            ),
            "receipts_error_count": receipt_model.search_count(error_receipt_domain),
            "receipts_error_drilldown": self._get_drilldown_action(
                "phantom.receipt", domain=error_receipt_domain, name=_("Receipts with errors"),
            ),
            "last_read_datetime": (
                company.phantom_last_read_datetime
                and fields.Datetime.to_string(company.phantom_last_read_datetime)
            ),
            "last_creation_datetime": (
                company.phantom_last_creation_date
                and fields.Datetime.to_string(company.phantom_last_creation_date)
            ),
        }
