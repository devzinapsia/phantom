import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import AccessError, UserError

from .phantom_api_client import PhantomAPIClient, PhantomAPIError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    phantom_url = fields.Char(string="Phantom API URL")
    phantom_user = fields.Char(string="Phantom API user")
    phantom_password = fields.Char(
        string="Phantom API password", groups="phantom_connector.group_phantom_manager"
    )
    phantom_enabled = fields.Boolean(string="Enable Phantom integration", default=False)
    phantom_processing_mode = fields.Selection(
        [("manual", "Manual"), ("automatic", "Automatic")],
        string="Processing mode", default="manual", required=True,
    )
    phantom_timezone = fields.Selection(
        _tz_get, string="Import timezone",
        help="Timezone used to evaluate 'Import time' below, for the "
        "automatic processing mode. Never assumed from the server; set "
        "it explicitly if it is not suggested automatically when Phantom "
        "is enabled.",
    )
    phantom_read_hour = fields.Float(
        string="Import time", default=2.0,
        help="Local time of day (in the timezone above) at which the "
        "automatic import cron runs for this company, once per day. Only "
        "used in automatic processing mode.",
    )
    phantom_sweep_window_days = fields.Integer(
        string="Sweep window (days)", default=7,
        help="How many days back are re-queried on every import run, to "
        "catch vouchers Phantom loaded late or modified after their own "
        "date.",
    )
    phantom_last_read_date = fields.Date(
        string="Last automatic import (local date)", copy=False,
        help="Local date (in the timezone above) the automatic cron last "
        "ran for this company. Used only to avoid running twice on the "
        "same local day; manual 'Import now' runs do not change it.",
    )
    phantom_last_read_datetime = fields.Datetime(
        string="Last successful Phantom read", copy=False,
        help="Set after every successful import, manual or automatic.",
    )
    phantom_last_creation_date = fields.Datetime(
        string="Last document creation from Phantom", copy=False,
        help="Set by phantom_account_bridge when it creates invoices/"
        "receipts from staging data. Empty ('Never') if that module is "
        "not installed, or nothing has been created yet.",
    )

    def _get_phantom_default_tz(self):
        """Suggest a timezone from the company's country. Returns False
        when the country's zones don't all share the same current UTC
        offset (e.g. the US, Brazil): unlike Argentina, whose many IANA
        zone names are all -03:00 today, those are genuinely ambiguous
        and must be set explicitly instead of guessed.
        """
        self.ensure_one()
        country_code = self.country_id.code
        if not country_code:
            return False
        tz_names = pytz.country_timezones.get(country_code.upper())
        if not tz_names:
            return False
        now = datetime.utcnow()
        offsets = {pytz.timezone(tz_name).utcoffset(now) for tz_name in tz_names}
        return tz_names[0] if len(offsets) == 1 else False

    def action_phantom_import(self):
        """Import pending Phantom invoices/receipts for every company in
        self, right now, regardless of processing mode. Used both by the
        manual 'Import now' dashboard button (interactive, raises on
        failure; available to group_phantom_user and
        group_phantom_manager alike) and, per company, by the automatic
        cron below.

        The actual read/write operations run under sudo() (see
        _phantom_import_one) since group_phantom_user has neither read
        access to phantom_password nor write access to res.company/
        phantom.invoice/phantom.receipt -- the explicit group check
        below is what actually gates who may call this method at all.
        """
        if not self.env.su and not self.env.user.has_group("phantom_connector.group_phantom_user"):
            raise AccessError(_("You are not allowed to trigger a Phantom import."))
        for company in self:
            if not company.phantom_enabled:
                raise UserError(
                    _("Phantom integration is not enabled for %(company)s.", company=company.name)
                )
            try:
                company._phantom_import_one()
            except PhantomAPIError as exc:
                raise UserError(str(exc)) from exc

    def _phantom_import_one(self):
        self.ensure_one()
        company = self.sudo()
        client = PhantomAPIClient(company.phantom_url, company.phantom_user, company.phantom_password)
        client.authenticate()

        today = fields.Date.context_today(company)
        desde = today - timedelta(days=company.phantom_sweep_window_days)

        invoice_rows = client.query_invoices(
            desde=desde.isoformat(), hasta=today.isoformat(), fecha_filtrar=1
        )
        self.env["phantom.invoice"].sudo()._phantom_upsert(invoice_rows, company)

        receipt_rows = client.query_receipts(
            desde=desde.isoformat(), hasta=today.isoformat(), fecha_filtrar=1
        )
        self.env["phantom.receipt"].sudo()._phantom_upsert(receipt_rows, company)

        company.write({
            "phantom_last_read_datetime": fields.Datetime.now(),
            "phantom_last_read_date": today,
        })

    def _cron_phantom_import(self):
        """Entry point for the automatic-mode cron. Companies in manual
        mode are skipped entirely -- the only way to import for those is
        the explicit 'Import now' action. Each company is isolated in
        its own try/except so one failure never blocks the rest.
        """
        companies = self.search([
            ("phantom_enabled", "=", True),
            ("phantom_processing_mode", "=", "automatic"),
        ])
        for company in companies:
            try:
                if not company._phantom_due_for_automatic_import():
                    continue
                company.action_phantom_import()
            except Exception as exc:
                _logger.exception(
                    "Phantom automatic import failed for company %s", company.display_name
                )
                company._phantom_notify_import_failure(exc)

    def _phantom_due_for_automatic_import(self):
        """True if this company hasn't run its automatic import yet
        today (in its own local timezone) and the configured import time
        has already passed. Being 'due' isn't tied to a fixed window, so
        a late or skipped cron tick still catches it later the same day
        instead of silently missing its only chance.
        """
        self.ensure_one()
        tz_name = self.phantom_timezone or self._get_phantom_default_tz()
        if not tz_name:
            return False
        now_local = pytz.utc.localize(fields.Datetime.now()).astimezone(pytz.timezone(tz_name))
        today = now_local.date()
        if self.phantom_last_read_date == today:
            return False
        configured_minutes = round(self.phantom_read_hour * 60)
        now_minutes = now_local.hour * 60 + now_local.minute
        return now_minutes >= configured_minutes

    def _phantom_notify_import_failure(self, exc):
        """Notify Phantom Administrators (the only ones who can see the
        Phantom credentials in the first place) that an automatic import
        failed. The error text is safe to include: PhantomAPIError
        messages never contain the configured password.
        """
        self.ensure_one()
        partner_ids = self.env.ref("phantom_connector.group_phantom_manager").users.partner_id.ids
        if not partner_ids:
            return
        self.env["mail.thread"].message_notify(
            partner_ids=partner_ids,
            subject=_("Phantom import failed for %(company)s", company=self.name),
            body=_(
                "The automatic Phantom import failed for %(company)s: %(error)s",
                company=self.name, error=str(exc),
            ),
            email_add_signature=False,
        )
