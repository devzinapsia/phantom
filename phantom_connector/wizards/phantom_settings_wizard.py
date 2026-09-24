from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get


class PhantomSettingsWizard(models.TransientModel):
    """Dedicated Phantom configuration screen, deliberately separate from
    Odoo's generic Settings page: that page (res.config.settings) is
    hard-restricted to base.group_system at the model-access level, with
    no way to open it up to a narrower 'Phantom Administrator' role. This
    wizard is gated by group_phantom_manager instead, so a company can
    delegate Phantom configuration without granting general Odoo
    administrator rights.

    There is no dedicated "Save" button: saving the wizard record through
    the standard form save control (like any other single-record form)
    writes straight through to res.company via sudo() in create()/write(),
    scoped to exactly the fields this wizard exposes -- not a blanket
    write grant on res.company for the group_phantom_manager group, which
    would be a much bigger access surface than intended.

    company_id always follows the current active company (env.company),
    like Odoo's own Settings screen: it is not user-editable here, so
    switching which company's settings you see means switching the active
    company first, not picking one on this form.
    """

    _name = "phantom.settings.wizard"
    _description = "Phantom Settings"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    phantom_enabled = fields.Boolean(string="Enable Phantom integration")
    phantom_url = fields.Char(string="Phantom API URL")
    phantom_user = fields.Char(string="Phantom API user")
    phantom_password = fields.Char(string="Phantom API password")
    phantom_processing_mode = fields.Selection(
        [("manual", "Manual"), ("automatic", "Automatic")], string="Processing mode",
    )
    phantom_timezone = fields.Selection(_tz_get, string="Import timezone")
    phantom_read_hour = fields.Float(string="Import time")
    phantom_sweep_window_days = fields.Integer(string="Sweep window (days)")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        company = (
            self.env["res.company"].browse(vals["company_id"])
            if vals.get("company_id") else self.env.company
        )
        vals.update(self._values_from_company(company))
        return vals

    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = _("Phantom settings")

    def _values_from_company(self, company):
        return {
            "phantom_enabled": company.phantom_enabled,
            "phantom_url": company.phantom_url,
            "phantom_user": company.phantom_user,
            "phantom_password": company.phantom_password,
            "phantom_processing_mode": company.phantom_processing_mode,
            "phantom_timezone": company.phantom_timezone or company._get_phantom_default_tz(),
            "phantom_read_hour": company.phantom_read_hour,
            "phantom_sweep_window_days": company.phantom_sweep_window_days,
        }

    def _phantom_settings_vals(self):
        self.ensure_one()
        return {
            "phantom_enabled": self.phantom_enabled,
            "phantom_url": self.phantom_url,
            "phantom_user": self.phantom_user,
            "phantom_password": self.phantom_password,
            "phantom_processing_mode": self.phantom_processing_mode,
            "phantom_timezone": self.phantom_timezone,
            "phantom_read_hour": self.phantom_read_hour,
            "phantom_sweep_window_days": self.phantom_sweep_window_days,
        }

    def _phantom_sync_to_company(self):
        for wizard in self:
            wizard.company_id.sudo().write(wizard._phantom_settings_vals())

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        wizards._phantom_sync_to_company()
        return wizards

    def write(self, vals):
        res = super().write(vals)
        self._phantom_sync_to_company()
        return res
