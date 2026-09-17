from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPhantomSettingsWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_wizard_loads_current_company_values(self):
        self.company.write({
            "phantom_enabled": True,
            "phantom_url": "http://phantom.example/api",
            "phantom_user": "existing_user",
        })
        wizard = self.env["phantom.settings.wizard"].create({"company_id": self.company.id})
        self.assertTrue(wizard.phantom_enabled)
        self.assertEqual(wizard.phantom_url, "http://phantom.example/api")
        self.assertEqual(wizard.phantom_user, "existing_user")

    def test_wizard_save_writes_to_company(self):
        wizard = self.env["phantom.settings.wizard"].create({
            "company_id": self.company.id,
            "phantom_enabled": True,
            "phantom_url": "http://phantom.example/api",
            "phantom_user": "api_user",
            "phantom_password": "api_pass",
            "phantom_processing_mode": "manual",
            "phantom_sweep_window_days": 5,
        })
        wizard.action_save()
        self.company.invalidate_recordset()

        self.assertTrue(self.company.phantom_enabled)
        self.assertEqual(self.company.phantom_url, "http://phantom.example/api")
        self.assertEqual(self.company.phantom_user, "api_user")
        self.assertEqual(self.company.phantom_password, "api_pass")
        self.assertEqual(self.company.phantom_sweep_window_days, 5)

    def test_group_phantom_user_cannot_access_settings_wizard(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom User",
            "login": "phantom_user_test",
            "email": "phantom_user_test@example.com",
            "group_ids": [Command.link(self.env.ref("phantom_connector.group_phantom_user").id)],
        })
        with self.assertRaises(AccessError):
            self.env["phantom.settings.wizard"].with_user(user).create({"company_id": self.company.id})

    def test_group_phantom_manager_can_access_settings_wizard(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom Manager",
            "login": "phantom_manager_test",
            "email": "phantom_manager_test@example.com",
            "group_ids": [Command.link(self.env.ref("phantom_connector.group_phantom_manager").id)],
        })
        wizard = self.env["phantom.settings.wizard"].with_user(user).create({"company_id": self.company.id})
        self.assertTrue(wizard)
