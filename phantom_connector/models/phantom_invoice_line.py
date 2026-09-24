from odoo import fields, models


class PhantomInvoiceLine(models.Model):
    """One parsed item from a Phantom invoice's 'Detalle' string. Embedded
    sub-record of phantom.invoice only -- no chatter, no standalone menu,
    same pattern as account.move.line.
    """

    _name = "phantom.invoice.line"
    _description = "Phantom Invoice Line"
    _order = "invoice_id, sequence, id"

    invoice_id = fields.Many2one(
        "phantom.invoice", string="Invoice", required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    article_code = fields.Char(string="Article code")
    description = fields.Char(string="Description")
    amount_untaxed = fields.Float(string="Net amount")
    tax_percent = fields.Float(string="Tax %")
    amount_total = fields.Float(string="Total")
