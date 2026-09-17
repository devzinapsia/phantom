from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    phantom_invoice_ids = fields.One2many(
        "phantom.invoice", "account_move_id", string="Phantom Invoice"
    )

    def action_view_phantom_invoice(self):
        self.ensure_one()
        phantom_invoice = self.phantom_invoice_ids[:1]
        return {
            "type": "ir.actions.act_window",
            "res_model": "phantom.invoice",
            "view_mode": "form",
            "res_id": phantom_invoice.id,
        }
