from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestPhantomDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Invoice = cls.env["phantom.invoice"]
        cls.Receipt = cls.env["phantom.receipt"]

        today = fields.Date.today()
        cls.this_month_date = today
        cls.last_month_date = today.replace(day=1) - timedelta(days=1)

        cls._create_invoice("D1", cls.this_month_date, 100.0, "pending")
        cls._create_invoice("D2", cls.this_month_date, 200.0, "processed")
        cls._create_invoice("D3", cls.last_month_date, 50.0, "pending")
        cls._create_invoice("D4", cls.this_month_date, 5.0, "error")
        cls._create_receipt("R1", cls.this_month_date, 10.0, "pending")
        cls._create_receipt("R2", cls.this_month_date, 20.0, "processed")
        cls._create_receipt("R3", cls.last_month_date, 15.0, "pending")
        cls._create_receipt("R4", cls.this_month_date, 8.0, "error")

    @classmethod
    def _create_invoice(cls, idt, invoice_date, amount, state):
        return cls.Invoice.create({
            "phantom_idt": idt,
            "company_id": cls.company.id,
            "invoice_date": invoice_date,
            "amount_total": amount,
            "state": state,
        })

    @classmethod
    def _create_receipt(cls, idt, receipt_date, amount, state):
        return cls.Receipt.create({
            "phantom_idt": idt,
            "company_id": cls.company.id,
            "receipt_date": receipt_date,
            "amount_total": amount,
            "state": state,
        })

    def test_dashboard_indicators(self):
        data = self.env["phantom.dashboard"].get_dashboard_data()

        self.assertEqual(data["invoices_this_month_count"], 3)
        self.assertEqual(data["invoices_this_month_amount"], 305.0)
        self.assertEqual(data["invoices_last_month_count"], 1)
        self.assertEqual(data["invoices_last_month_amount"], 50.0)
        self.assertEqual(data["invoices_pending_count"], 2)
        self.assertEqual(data["invoices_error_count"], 1)
        self.assertEqual(data["receipts_this_month_count"], 3)
        self.assertEqual(data["receipts_this_month_amount"], 38.0)
        self.assertEqual(data["receipts_last_month_count"], 1)
        self.assertEqual(data["receipts_last_month_amount"], 15.0)
        self.assertEqual(data["receipts_pending_count"], 2)
        self.assertEqual(data["receipts_error_count"], 1)
        self.assertEqual(data["invoices_pending_drilldown"]["res_model"], "phantom.invoice")
        self.assertEqual(data["receipts_pending_drilldown"]["res_model"], "phantom.receipt")
        self.assertEqual(data["invoices_this_month_drilldown"]["res_model"], "phantom.invoice")
        self.assertEqual(data["invoices_last_month_drilldown"]["res_model"], "phantom.invoice")
        self.assertEqual(data["receipts_this_month_drilldown"]["res_model"], "phantom.receipt")
        self.assertEqual(data["receipts_last_month_drilldown"]["res_model"], "phantom.receipt")
        self.assertEqual(data["invoices_error_drilldown"]["res_model"], "phantom.invoice")
        self.assertEqual(data["receipts_error_drilldown"]["res_model"], "phantom.receipt")

    def test_dashboard_last_run_indicators(self):
        now = fields.Datetime.now()
        self.company.phantom_last_read_datetime = now
        data = self.env["phantom.dashboard"].get_dashboard_data()
        self.assertEqual(data["last_read_datetime"], fields.Datetime.to_string(now))
        self.assertFalse(data["last_creation_datetime"])
