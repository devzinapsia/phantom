from odoo import Command, fields, models


class PhantomSettingsWizard(models.TransientModel):
    _inherit = "phantom.settings.wizard"

    phantom_sales_journal_id = fields.Many2one("account.journal", string="Sales journal")
    phantom_receipt_journal_id = fields.Many2one("account.journal", string="Receipt journal")
    phantom_default_product_id = fields.Many2one("product.product", string="Default product")
    phantom_analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic account")
    phantom_classification_id = fields.Many2one("account.move.classification", string="Classification")
    phantom_create_hour = fields.Float(string="Creation time")
    phantom_notify_user_ids = fields.Many2many("res.users", string="Responsible users")

    def _values_from_company(self, company):
        vals = super()._values_from_company(company)
        vals.update({
            "phantom_sales_journal_id": company.phantom_sales_journal_id.id,
            "phantom_receipt_journal_id": company.phantom_receipt_journal_id.id,
            "phantom_default_product_id": company.phantom_default_product_id.id,
            "phantom_analytic_account_id": company.phantom_analytic_account_id.id,
            "phantom_classification_id": company.phantom_classification_id.id,
            "phantom_create_hour": company.phantom_create_hour,
            "phantom_notify_user_ids": [Command.set(company.phantom_notify_user_ids.ids)],
        })
        return vals

    def _phantom_settings_vals(self):
        vals = super()._phantom_settings_vals()
        vals.update({
            "phantom_sales_journal_id": self.phantom_sales_journal_id.id,
            "phantom_receipt_journal_id": self.phantom_receipt_journal_id.id,
            "phantom_default_product_id": self.phantom_default_product_id.id,
            "phantom_analytic_account_id": self.phantom_analytic_account_id.id,
            "phantom_classification_id": self.phantom_classification_id.id,
            "phantom_create_hour": self.phantom_create_hour,
            "phantom_notify_user_ids": [Command.set(self.phantom_notify_user_ids.ids)],
        })
        return vals
