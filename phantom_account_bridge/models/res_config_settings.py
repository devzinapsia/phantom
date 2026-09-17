from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    phantom_sales_journal_id = fields.Many2one(
        related="company_id.phantom_sales_journal_id", readonly=False
    )
    phantom_receipt_journal_id = fields.Many2one(
        related="company_id.phantom_receipt_journal_id", readonly=False
    )
    phantom_default_product_id = fields.Many2one(
        related="company_id.phantom_default_product_id", readonly=False
    )
    phantom_analytic_account_id = fields.Many2one(
        related="company_id.phantom_analytic_account_id", readonly=False
    )
    phantom_classification_id = fields.Many2one(
        related="company_id.phantom_classification_id", readonly=False
    )
    phantom_create_hour = fields.Float(
        related="company_id.phantom_create_hour", readonly=False
    )
