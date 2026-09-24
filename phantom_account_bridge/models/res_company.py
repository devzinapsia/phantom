import logging

import pytz

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    phantom_sales_journal_id = fields.Many2one(
        "account.journal", string="Sales journal", domain="[('type', '=', 'sale')]",
    )
    phantom_receipt_journal_id = fields.Many2one(
        "account.journal", string="Receipt journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    phantom_default_product_id = fields.Many2one(
        "product.product", string="Default product",
        help="The only product used on invoice lines created by this "
        "integration -- Phantom does not report products mappable to Odoo, "
        "only free text in 'Detalle'.",
    )
    phantom_analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Analytic account",
        help="Applied at 100% to every invoice line created by this "
        "integration.",
    )
    phantom_classification_id = fields.Many2one(
        "account.move.classification", string="Classification",
        help="Applied to every invoice created by this integration, to "
        "make them easy to filter/report on.",
    )
    phantom_create_hour = fields.Float(
        string="Creation time", default=3.0,
        help="Local time of day (in the 'Import timezone' setting above) at "
        "which the automatic document-creation cron runs for this company, "
        "once per day. Only used in automatic processing mode.",
    )
    phantom_last_creation_run_date = fields.Date(
        string="Last automatic creation (local date)", copy=False,
        help="Local date the automatic creation cron last ran for this "
        "company. Used only to avoid running twice on the same local day; "
        "manual creation runs do not change it.",
    )

    def action_phantom_create(self):
        """Create real invoices/receipts for every pending Phantom record
        of every company in self, right now, regardless of processing
        mode. Used both by the manual 'Process now' dashboard button
        (interactive, raises on failure; available to group_phantom_user
        and group_phantom_manager alike, same as action_phantom_import in
        phantom_connector) and, per company, by the automatic cron below.

        The actual document creation runs under sudo() (see
        _phantom_create_one), since group_phantom_user has neither create
        access on account.move/account.payment/res.partner nor write
        access to res.company -- the explicit group check below is what
        actually gates who may call this method at all.
        """
        if not self.env.su and not self.env.user.has_group("phantom_connector.group_phantom_user"):
            raise AccessError(_("You are not allowed to trigger Phantom document creation."))
        for company in self:
            if not company.phantom_enabled:
                raise UserError(
                    _("Phantom integration is not enabled for %(company)s.", company=company.name)
                )
            company._phantom_create_one()

    def _phantom_process_invoices(self, invoices):
        for invoice in invoices:
            try:
                invoice._phantom_create_document(self)
            except Exception as exc:
                _logger.exception(
                    "Failed to create an account.move from phantom.invoice %s", invoice.id
                )
                invoice.write({"state": "error", "error_message": str(exc)})

    def _phantom_process_receipts(self, receipts):
        for receipt in receipts:
            try:
                receipt._phantom_create_document(self)
            except Exception as exc:
                _logger.exception(
                    "Failed to create an account.payment from phantom.receipt %s", receipt.id
                )
                receipt.write({"state": "error", "error_message": str(exc)})

    def _phantom_retry_reconciliation(self):
        """Retry reconciliation for invoices whose associated receipt
        wasn't processed yet at creation time -- including ones from this
        same run, now that their receipts may have been processed too.
        """
        self.ensure_one()
        retry_invoices = self.env["phantom.invoice"].search([
            ("company_id", "=", self.id), ("pending_reconciliation", "=", True),
        ])
        for invoice in retry_invoices:
            try:
                invoice._phantom_try_reconcile(self)
            except Exception:
                _logger.exception(
                    "Failed to retry reconciliation for phantom.invoice %s", invoice.id
                )

    def _phantom_create_one(self):
        self.ensure_one()
        company = self.sudo()
        invoice_model = self.env["phantom.invoice"].sudo()
        receipt_model = self.env["phantom.receipt"].sudo()

        company._phantom_process_invoices(invoice_model.search([
            ("company_id", "=", self.id), ("state", "=", "pending"),
        ]))
        company._phantom_process_receipts(receipt_model.search([
            ("company_id", "=", self.id), ("state", "=", "pending"),
        ]))
        company._phantom_retry_reconciliation()
        company.write({
            "phantom_last_creation_date": fields.Datetime.now(),
            "phantom_last_creation_run_date": fields.Date.context_today(company),
        })

    def action_phantom_create_batch(self, batch_size=50):
        """Process up to batch_size pending Phantom records for this
        company and return progress info -- one bounded chunk of work per
        call, meant to be looped by the client while it renders a progress
        bar (same pattern as Odoo's own base_import: the client drives the
        loop and tracks progress itself, not a background/cron job).

        Same access rules as action_phantom_create() (explicit group
        check, sudo'd document creation) -- see its docstring.
        """
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group("phantom_connector.group_phantom_user"):
            raise AccessError(_("You are not allowed to trigger Phantom document creation."))
        if not self.phantom_enabled:
            raise UserError(
                _("Phantom integration is not enabled for %(company)s.", company=self.name)
            )

        company = self.sudo()
        invoice_model = self.env["phantom.invoice"].sudo()
        receipt_model = self.env["phantom.receipt"].sudo()

        pending_invoices = invoice_model.search([
            ("company_id", "=", self.id), ("state", "=", "pending"),
        ], limit=batch_size)
        company._phantom_process_invoices(pending_invoices)

        remaining_slots = batch_size - len(pending_invoices)
        pending_receipts = receipt_model.browse()
        if remaining_slots > 0:
            pending_receipts = receipt_model.search([
                ("company_id", "=", self.id), ("state", "=", "pending"),
            ], limit=remaining_slots)
            company._phantom_process_receipts(pending_receipts)

        remaining = (
            invoice_model.search_count([("company_id", "=", self.id), ("state", "=", "pending")])
            + receipt_model.search_count([("company_id", "=", self.id), ("state", "=", "pending")])
        )
        done = not remaining
        if done:
            company._phantom_retry_reconciliation()
            company.write({
                "phantom_last_creation_date": fields.Datetime.now(),
                "phantom_last_creation_run_date": fields.Date.context_today(company),
            })
        return {
            "processed": len(pending_invoices) + len(pending_receipts),
            "remaining": remaining,
            "done": done,
        }

    def _cron_phantom_create(self):
        """Entry point for the automatic-mode creation cron. Companies in
        manual mode are skipped -- the only way to create documents for
        those is the explicit 'Import now'-equivalent action (a manual
        button is not required by scope here: processing pending records
        happens automatically as part of every creation run once enabled).
        Each company is isolated in its own try/except.
        """
        companies = self.search([
            ("phantom_enabled", "=", True),
            ("phantom_processing_mode", "=", "automatic"),
        ])
        for company in companies:
            try:
                if not company._phantom_due_for_automatic_creation():
                    continue
                company.action_phantom_create()
            except Exception as exc:
                _logger.exception(
                    "Phantom automatic document creation failed for company %s",
                    company.display_name,
                )
                company._phantom_notify_creation_failure(exc)

    def _phantom_due_for_automatic_creation(self):
        self.ensure_one()
        tz_name = self.phantom_timezone or self._get_phantom_default_tz()
        if not tz_name:
            return False
        now_local = pytz.utc.localize(fields.Datetime.now()).astimezone(pytz.timezone(tz_name))
        today = now_local.date()
        if self.phantom_last_creation_run_date == today:
            return False
        configured_minutes = round(self.phantom_create_hour * 60)
        now_minutes = now_local.hour * 60 + now_local.minute
        return now_minutes >= configured_minutes

    def _phantom_notify_creation_failure(self, exc):
        self.ensure_one()
        partner_ids = self.env.ref("phantom_connector.group_phantom_manager").users.partner_id.ids
        if not partner_ids:
            return
        self.env["mail.thread"].message_notify(
            partner_ids=partner_ids,
            subject=_("Phantom document creation failed for %(company)s", company=self.name),
            body=_(
                "The automatic Phantom document creation failed for "
                "%(company)s: %(error)s",
                company=self.name, error=str(exc),
            ),
            email_add_signature=False,
        )
