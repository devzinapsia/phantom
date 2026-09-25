import logging

import pytz

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# Every creation run retries "error" records alongside "pending" ones, not
# just "pending" -- a record stuck in "error" (e.g. a fixable config issue,
# like a missing AFIP service period) should get another shot on the very
# next run instead of staying stuck forever until someone finds and
# manually resets it.
_RETRYABLE_STATES = ("pending", "error")


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
    phantom_notify_user_ids = fields.Many2many(
        "res.users", string="Responsible users",
        help="Notified by email every time Phantom document creation "
        "finishes (manual 'Process now' or the automatic cron) with at "
        "least one record processed -- whether it succeeded, how many "
        "invoices/receipts were created, and how many need review. Empty "
        "means no notification is sent.",
    )

    def action_phantom_create(self, trigger="manual"):
        """Create real invoices/receipts for every pending Phantom record
        of every company in self, right now, regardless of processing
        mode. Available to group_phantom_user and group_phantom_manager
        alike, same as action_phantom_import in phantom_connector; called,
        per company, by the automatic cron below (trigger="automatic")
        and directly by tests/callers simulating a manual all-at-once
        trigger (trigger="manual", the default) -- the interactive 'Process
        now' dashboard button itself drives action_phantom_create_batch
        instead, for the progress bar.

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
            company._phantom_create_one(trigger)

    def _phantom_process_invoices(self, invoices, trigger):
        """Returns (succeeded, failed) counts -- counted directly off the
        recordset that was actually attempted, not re-derived later by
        guessing at a time window: a write_date-vs-timestamp comparison is
        unreliable within a single transaction (Postgres's own now() can
        stay frozen at transaction start rather than advancing in real
        time), so it must not be relied on for this. trigger ("manual" or
        "automatic") is passed straight through to
        phantom.invoice._phantom_create_document, which logs it on the
        created account.move's chatter.
        """
        succeeded = failed = 0
        for invoice in invoices:
            try:
                invoice._phantom_create_document(self, trigger)
                succeeded += 1
            except Exception as exc:
                _logger.exception(
                    "Failed to create an account.move from phantom.invoice %s", invoice.id
                )
                invoice.write({"state": "error", "error_message": str(exc)})
                failed += 1
        return succeeded, failed

    def _phantom_process_receipts(self, receipts, trigger):
        """See _phantom_process_invoices's docstring."""
        succeeded = failed = 0
        for receipt in receipts:
            try:
                receipt._phantom_create_document(self, trigger)
                succeeded += 1
            except Exception as exc:
                _logger.exception(
                    "Failed to create an account.payment from phantom.receipt %s", receipt.id
                )
                receipt.write({"state": "error", "error_message": str(exc)})
                failed += 1
        return succeeded, failed

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

    def _phantom_create_one(self, trigger="manual"):
        self.ensure_one()
        company = self.sudo()
        invoice_model = self.env["phantom.invoice"].sudo()
        receipt_model = self.env["phantom.receipt"].sudo()

        invoices_processed, invoices_error = company._phantom_process_invoices(invoice_model.search([
            ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
        ]), trigger)
        receipts_processed, receipts_error = company._phantom_process_receipts(receipt_model.search([
            ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
        ]), trigger)
        company._phantom_retry_reconciliation()
        company.write({
            "phantom_last_creation_date": fields.Datetime.now(),
            "phantom_last_creation_run_date": fields.Date.context_today(company),
        })
        company._phantom_notify_creation_summary(
            invoices_processed, invoices_error, receipts_processed, receipts_error
        )

    def action_phantom_create_batch(
        self, batch_size=50,
        invoices_processed=0, invoices_error=0, receipts_processed=0, receipts_error=0,
        last_invoice_id=0, last_receipt_id=0,
    ):
        """Process up to batch_size pending *and* error-state Phantom
        records for this company (see _RETRYABLE_STATES) and return
        progress info -- one bounded chunk of work per call, meant to be
        looped by the client while it renders a progress bar (same
        pattern as Odoo's own base_import: the client drives the loop and
        tracks progress itself, not a background/cron job).

        The four *_processed/*_error kwargs are the running totals from
        every call so far in this run, passed back in by the caller on
        every call after the first (using this method's own returned
        values) -- accumulated this way, not via a "since when" timestamp
        comparison against write_date, which is unreliable within a
        transaction (see _phantom_process_invoices's docstring). Used
        for the completion-summary notification
        (_phantom_notify_creation_summary) once the whole run is done.

        last_invoice_id/last_receipt_id are an id cursor, also threaded
        back in by the caller the same way: since error records stay
        retryable even after failing again, selecting "the next batch_size
        retryable records" by state alone would keep re-selecting the same
        permanently-broken records at the head of the id order forever,
        looping infinitely with zero progress. Restricting each call to
        id > cursor guarantees every record is attempted at most once per
        run (a fresh cursor each time the button is pressed, or each cron
        run) and that the loop always terminates, whether or not every
        record actually succeeds -- a record still in "error" after this
        sweep gets picked up again on the *next* run, not this one.

        Always driven by the interactive 'Process now' button, so every
        document created through here is logged on its own chatter as a
        manual-trigger creation (see
        phantom.staging.mixin._phantom_creation_chatter_message).

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

        retryable_invoices = invoice_model.search([
            ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
            ("id", ">", last_invoice_id),
        ], limit=batch_size, order="id")
        batch_invoices_processed, batch_invoices_error = company._phantom_process_invoices(
            retryable_invoices, "manual"
        )
        invoices_processed += batch_invoices_processed
        invoices_error += batch_invoices_error
        if retryable_invoices:
            last_invoice_id = max(retryable_invoices.ids)

        remaining_slots = batch_size - len(retryable_invoices)
        retryable_receipts = receipt_model.browse()
        if remaining_slots > 0:
            retryable_receipts = receipt_model.search([
                ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
                ("id", ">", last_receipt_id),
            ], limit=remaining_slots, order="id")
            batch_receipts_processed, batch_receipts_error = company._phantom_process_receipts(
                retryable_receipts, "manual"
            )
            receipts_processed += batch_receipts_processed
            receipts_error += batch_receipts_error
            if retryable_receipts:
                last_receipt_id = max(retryable_receipts.ids)

        remaining = (
            invoice_model.search_count([
                ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
                ("id", ">", last_invoice_id),
            ])
            + receipt_model.search_count([
                ("company_id", "=", self.id), ("state", "in", _RETRYABLE_STATES),
                ("id", ">", last_receipt_id),
            ])
        )
        done = not remaining
        if done:
            company._phantom_retry_reconciliation()
            company.write({
                "phantom_last_creation_date": fields.Datetime.now(),
                "phantom_last_creation_run_date": fields.Date.context_today(company),
            })
            company._phantom_notify_creation_summary(
                invoices_processed, invoices_error, receipts_processed, receipts_error
            )
        return {
            "processed": len(retryable_invoices) + len(retryable_receipts),
            "remaining": remaining,
            "done": done,
            "invoices_processed": invoices_processed,
            "invoices_error": invoices_error,
            "receipts_processed": receipts_processed,
            "receipts_error": receipts_error,
            "last_invoice_id": last_invoice_id,
            "last_receipt_id": last_receipt_id,
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
                company.action_phantom_create(trigger="automatic")
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

    def _phantom_notify_creation_summary(
        self, invoices_processed, invoices_error, receipts_processed, receipts_error,
    ):
        """Email phantom_notify_user_ids a summary of everything processed
        in this run (both success and error counts, counted directly off
        the recordsets actually attempted -- see
        _phantom_process_invoices's docstring for why not a timestamp
        comparison), once a creation run (manual 'Process now' or the
        automatic cron) finishes -- not just on a hard failure, unlike
        _phantom_notify_creation_failure below, which is for the whole
        run raising before it could even finish. Silently does nothing if
        no one is configured to be notified, or if nothing was actually
        processed this run (avoids a "nothing happened" email every time
        the cron finds no pending records).
        """
        self.ensure_one()
        recipients = self.phantom_notify_user_ids.partner_id
        if not recipients:
            return
        if not (invoices_processed or invoices_error or receipts_processed or receipts_error):
            return

        has_errors = bool(invoices_error or receipts_error)
        subject = (
            _("Phantom processing finished with errors for %(company)s", company=self.name)
            if has_errors else
            _("Phantom processing finished successfully for %(company)s", company=self.name)
        )
        body = _(
            "Invoices processed: %(invoices_processed)s (errors: %(invoices_error)s)<br/>"
            "Receipts processed: %(receipts_processed)s (errors: %(receipts_error)s)<br/>"
            "%(review_note)s",
            invoices_processed=invoices_processed,
            invoices_error=invoices_error,
            receipts_processed=receipts_processed,
            receipts_error=receipts_error,
            review_note=(
                _(
                    "Some records need review -- check the 'Error' filter on "
                    "Phantom Invoices/Receipts."
                )
                if has_errors else _("No errors.")
            ),
        )
        self.env["mail.thread"].message_notify(
            partner_ids=recipients.ids,
            subject=subject,
            body=body,
            email_add_signature=False,
        )

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
