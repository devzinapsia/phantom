from datetime import timedelta

from odoo import api, fields, models


class PhantomDashboard(models.TransientModel):
    """Read-only overview of the Phantom integration for the current
    company. Opened as a fresh, unsaved record every time: every field is
    either a default or a non-stored compute, so there is nothing
    meaningful to persist.
    """

    _name = "phantom.dashboard"
    _description = "Phantom Dashboard"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    invoices_this_month_count = fields.Integer(
        string="Invoices this month", compute="_compute_indicators"
    )
    invoices_last_month_count = fields.Integer(
        string="Invoices last month", compute="_compute_indicators"
    )
    invoices_this_month_amount = fields.Monetary(
        string="Amount this month", compute="_compute_indicators"
    )
    invoices_last_month_amount = fields.Monetary(
        string="Amount last month", compute="_compute_indicators"
    )
    invoices_pending_count = fields.Integer(
        string="Pending invoices", compute="_compute_indicators"
    )
    receipts_pending_count = fields.Integer(
        string="Pending receipts", compute="_compute_indicators"
    )
    last_read_datetime = fields.Datetime(
        string="Last successful Phantom read", compute="_compute_indicators"
    )
    last_creation_datetime = fields.Datetime(
        string="Last document creation from Phantom", compute="_compute_indicators"
    )

    @api.depends("company_id")
    def _compute_indicators(self):
        invoice_model = self.env["phantom.invoice"]
        receipt_model = self.env["phantom.receipt"]
        for rec in self:
            company = rec.company_id
            today = fields.Date.context_today(rec)
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

            rec.invoices_this_month_count = invoice_model.search_count(this_month_domain)
            rec.invoices_last_month_count = invoice_model.search_count(last_month_domain)

            this_month_rows = invoice_model._read_group(this_month_domain, [], ["amount_total:sum"])
            rec.invoices_this_month_amount = this_month_rows[0][0] if this_month_rows else 0.0
            last_month_rows = invoice_model._read_group(last_month_domain, [], ["amount_total:sum"])
            rec.invoices_last_month_amount = last_month_rows[0][0] if last_month_rows else 0.0

            rec.invoices_pending_count = invoice_model.search_count([
                ("company_id", "=", company.id), ("state", "=", "pending"),
            ])
            rec.receipts_pending_count = receipt_model.search_count([
                ("company_id", "=", company.id), ("state", "=", "pending"),
            ])

            rec.last_read_datetime = company.phantom_last_read_datetime
            rec.last_creation_datetime = company.phantom_last_creation_date
