from odoo import api, fields, models
from odoo.addons.base.models.res_partner import _tz_get


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    phantom_url = fields.Char(related="company_id.phantom_url", readonly=False)
    phantom_user = fields.Char(related="company_id.phantom_user", readonly=False)
    phantom_password = fields.Char(related="company_id.phantom_password", readonly=False)
    phantom_enabled = fields.Boolean(related="company_id.phantom_enabled", readonly=False)
    phantom_processing_mode = fields.Selection(
        related="company_id.phantom_processing_mode", readonly=False
    )
    phantom_read_hour = fields.Float(related="company_id.phantom_read_hour", readonly=False)
    phantom_sweep_window_days = fields.Integer(
        related="company_id.phantom_sweep_window_days", readonly=False
    )
    # Not a plain related field: get_values()/set_values() below suggest a
    # default from the company's country when nothing is stored yet
    # (mirrors account_payment_due_notify's identical pattern), which a
    # related field cannot do since it always recomputes from the (still
    # empty) target on every read, discarding any suggested value.
    phantom_timezone = fields.Selection(
        _tz_get, string="Import timezone",
        help="Timezone used to evaluate 'Import time' above, for the "
        "automatic processing mode. Never assumed from the server; set "
        "it explicitly if it is not suggested automatically when Phantom "
        "is enabled.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        company = self.env.company
        res["phantom_timezone"] = company.phantom_timezone or company._get_phantom_default_tz()
        return res

    def set_values(self):
        super().set_values()
        self.env.company.phantom_timezone = self.phantom_timezone
