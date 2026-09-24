from odoo import fields, models


class PhantomReceipt(models.Model):
    _inherit = "phantom.receipt"

    account_payment_id = fields.Many2one(
        "account.payment", string="Payment", readonly=True, copy=False
    )

    def action_view_account_payment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.account_payment_id.id,
        }

    def _phantom_create_document(self, company, trigger):
        self.ensure_one()
        partner = self._phantom_get_or_create_partner(company)

        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "company_id": company.id,
            "journal_id": company.phantom_receipt_journal_id.id,
            "amount": self.amount_total,
            "date": self.receipt_date,
            "memo": self.reference or self.comp_number,
        })
        payment.action_post()
        payment.message_post(body=self._phantom_creation_chatter_message(trigger))
        self.write({"account_payment_id": payment.id, "partner_id": partner.id, "state": "processed"})
        return payment
