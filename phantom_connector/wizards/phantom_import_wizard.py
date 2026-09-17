from odoo import _, fields, models


class PhantomImportWizard(models.TransientModel):
    """Trigger a Phantom import for the current company right now,
    regardless of its processing mode -- useful both for manual-mode
    companies (the only way they ever import) and to force an
    out-of-schedule run for automatic-mode companies.
    """

    _name = "phantom.import.wizard"
    _description = "Import Now from Phantom"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    def action_import_now(self):
        self.ensure_one()
        self.company_id.action_phantom_import()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Phantom import finished"),
                "message": _(
                    "Invoices and receipts for %(company)s were imported "
                    "from Phantom.", company=self.company_id.name,
                ),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
