import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PhantomStagingMixin(models.AbstractModel):
    """Shared upsert-by-IDT logic for phantom.invoice and phantom.receipt.

    Each row from the Phantom API is processed independently: a failure
    on one row (e.g. an unparseable date) is logged and skipped, never
    stopping the rest of the batch. Upserting an existing record never
    touches its 'state', so a record already moved past 'pending' by
    phantom_account_bridge is never reopened by a later import.
    """

    _name = "phantom.staging.mixin"
    _description = "Phantom Staging Upsert Mixin"

    def _phantom_vals_from_row(self, row):
        """Return the write/create vals for one Phantom API row, mapping
        its keys to this model's fields. Must not include 'phantom_idt',
        'company_id' or 'state' -- those are set by _phantom_upsert.
        """
        raise NotImplementedError

    @staticmethod
    def _phantom_clean_date(value):
        """Phantom's real API (confirmed against live responses, not just
        the generic manual) uses MySQL's zero-date placeholder
        ('0000-00-00') for an unset date, and some date fields come back
        with a time component even where only a date is expected here --
        take just the date part, or False for an empty/placeholder value.
        """
        if not value:
            return False
        date_part = value[:10]
        if date_part == "0000-00-00":
            return False
        return date_part

    @staticmethod
    def _phantom_clean_datetime(value):
        """Some Phantom datetime fields come back as a bare date (no time
        component); Odoo's ORM expects a full 'YYYY-MM-DD HH:MM:SS' string
        when writing a Datetime field from a plain string.
        """
        if not value:
            return False
        if value[:10] == "0000-00-00":
            return False
        return value if len(value) > 10 else value + " 00:00:00"

    def _phantom_upsert(self, rows, company):
        for row in rows:
            idt = row.get("IDT")
            if not idt:
                _logger.warning(
                    "Skipping %s row with no IDT for company %s: %s",
                    self._name, company.display_name, row,
                )
                continue
            try:
                vals = self._phantom_vals_from_row(row)
                existing = self.search(
                    [("phantom_idt", "=", idt), ("company_id", "=", company.id)], limit=1
                )
                if existing:
                    existing.write(vals)
                else:
                    vals.update({"phantom_idt": idt, "company_id": company.id})
                    self.create(vals)
            except Exception:
                _logger.exception(
                    "Failed to import %s IDT=%s for company %s",
                    self._name, idt, company.display_name,
                )
