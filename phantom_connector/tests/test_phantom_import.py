from datetime import date
from unittest.mock import patch

from odoo.tests.common import TransactionCase

SAMPLE_INVOICE_ROW = {
    "IDT": "1001",
    "Tipo": "Factura",
    "Tipo_Comp": "A",
    "P_venta": "0001",
    "Nro_Comp": "00000123",
    "Fecha": "2026-09-01",
    "Fecha_Transaccion": "2026-09-01 10:00:00",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30111222333",
    "Dirección": "Calle Falsa 123",
    "Ciudad": "CABA",
    "Moneda": "PES",
    "Cotización": 1.0,
    "Detalle": "1, Internet 20MB, 1000.00,21.00,1210.00;",
    "Importe_Neto": 1000.00,
    "Importe_IVA": 210.00,
    "Importe_Total": 1210.00,
    "Primer_Vto": "2026-09-15",
    "Segundo_Vto": "2026-09-30",
    "Comp_Asociado": "",
    "Suc_ID": "0",
}

SAMPLE_RECEIPT_ROW = {
    "IDT": "2001",
    "Nro_Comp": "REC-0001",
    "Fecha": "2026-09-01",
    "Fecha_Transaccion": "2026-09-01 11:00:00",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30111222333",
    "Dirección": "Calle Falsa 123",
    "Ciudad": "CABA",
    "Moneda": "PES",
    "Cotización": 1.0,
    "Detalle": "",
    "Importe_Total": 1210.00,
    "Medio_Pago": "Transferencia",
    "Referencia": "REF-1",
    "Suc_ID": "0",
}


class TestPhantomImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            "phantom_enabled": True,
            "phantom_url": "http://phantom.example/api",
            "phantom_user": "api_user",
            "phantom_password": "api_pass",
        })

    def _mock_client(self, invoice_rows=None, receipt_rows=None):
        patcher = patch.multiple(
            "odoo.addons.phantom_connector.models.phantom_api_client.PhantomAPIClient",
            authenticate=lambda self: "token123",
            query_invoices=lambda self, **kw: invoice_rows or [],
            query_receipts=lambda self, **kw: receipt_rows or [],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_import_new_invoice_creates_pending(self):
        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.action_phantom_import()

        invoice = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, "pending")
        self.assertEqual(invoice.partner_name, "Acme SA")
        self.assertEqual(invoice.amount_total, 1210.00)
        self.assertEqual(invoice.due_date_1, date(2026, 9, 15))
        self.assertEqual(invoice.due_date_2, date(2026, 9, 30))

    def test_import_new_receipt_creates_pending(self):
        self._mock_client(receipt_rows=[SAMPLE_RECEIPT_ROW])
        self.company.action_phantom_import()

        receipt = self.env["phantom.receipt"].search([("phantom_idt", "=", "2001")])
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.state, "pending")
        self.assertEqual(receipt.payment_method, "Transferencia")

    def test_reimport_same_idt_updates_not_duplicates(self):
        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.action_phantom_import()

        updated_row = dict(SAMPLE_INVOICE_ROW, RS="Acme SA Updated")
        self._mock_client(invoice_rows=[updated_row])
        self.company.action_phantom_import()

        invoices = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.partner_name, "Acme SA Updated")

    def test_reimport_processed_does_not_revert_state(self):
        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.action_phantom_import()

        invoice = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        invoice.state = "processed"

        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.action_phantom_import()

        invoice.invalidate_recordset()
        self.assertEqual(invoice.state, "processed")

    def test_disabled_company_no_http_call(self):
        self.company.phantom_enabled = False
        with patch(
            "odoo.addons.phantom_connector.models.phantom_api_client.requests.get"
        ) as mock_get:
            self.env["res.company"]._cron_phantom_import()
            mock_get.assert_not_called()

    def test_cron_respects_manual_mode(self):
        self.company.phantom_processing_mode = "manual"
        with patch(
            "odoo.addons.phantom_connector.models.res_company.ResCompany._phantom_import_one"
        ) as mock_import:
            self.env["res.company"]._cron_phantom_import()
            mock_import.assert_not_called()

    def test_cron_triggers_automatic_mode_when_due(self):
        self.company.write({
            "phantom_processing_mode": "automatic",
            "phantom_timezone": "America/Argentina/Buenos_Aires",
            "phantom_read_hour": 0.0,
            "phantom_last_read_date": False,
        })
        with patch(
            "odoo.addons.phantom_connector.models.res_company.ResCompany._phantom_import_one"
        ) as mock_import:
            self.env["res.company"]._cron_phantom_import()
            mock_import.assert_called_once()
