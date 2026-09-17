from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    phantom_receipt_ids = fields.One2many(
        "phantom.receipt", "account_payment_id", string="Phantom Receipt"
    )

    def action_view_phantom_receipt(self):
        self.ensure_one()
        phantom_receipt = self.phantom_receipt_ids[:1]
        return {
            "type": "ir.actions.act_window",
            "res_model": "phantom.receipt",
            "view_mode": "form",
            "res_id": phantom_receipt.id,
        }
