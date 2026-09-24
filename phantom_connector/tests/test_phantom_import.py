from datetime import date, datetime
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

# Field names and shapes below are confirmed against real API responses,
# not just the generic PDF manual: "Fecha" comes back with a time
# component, "Fecha_Transaccion" without one, unset due dates use MySQL's
# "0000-00-00" placeholder, and several field names lack the accents (or
# differ entirely, e.g. "Comp_Pago") that the manual uses.
SAMPLE_INVOICE_ROW = {
    "IDT": "1001",
    "Tipo": "Factura",
    "Tipo_Comp": "A",
    "P_Venta": "0001",
    "Nro_Comp": "00000123",
    "Fecha": "2026-09-01 10:02:14",
    "Fecha_Transaccion": "2026-09-01",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30111222333",
    "Direccion": "Calle Falsa 123",
    "Ciudad": "CABA",
    "Moneda": "PES",
    "Cotizacion": 1.0,
    # Real production Detalle values are overwhelmingly multi-item (~99%
    # of ~8000 real invoices checked), so the sample reflects that instead
    # of a single-item shape -- confirmed against the live API.
    "Detalle": "1, Internet 20MB, 1000.00,21.00,1210.00;2,WiFi Router,-100.00,21.00,-121.00;",
    "Importe_Neto": 1000.00,
    "Importe_IVA": 210.00,
    "Importe_Total": 1210.00,
    "Primer_Vto": "2026-09-15",
    "Segundo_Vto": "0000-00-00",
    "Comp_Pago": "0001-00000456;",
    "Suc_ID": "0",
    "CAE": "86349888860306",
    "CAE_Vto": "2026-09-11",
}

SAMPLE_RECEIPT_ROW = {
    "IDT": "2001",
    "Nro_Comp": "REC-0001",
    "Fecha": "2026-09-01 11:30:00",
    "Fecha_Transaccion": "2026-09-01",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30111222333",
    "Direccion": "Calle Falsa 123",
    "Ciudad": "CABA",
    "Moneda": "PES",
    "Cotizacion": 1.0,
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
        self.assertEqual(invoice.point_of_sale, "0001")
        self.assertEqual(invoice.address, "Calle Falsa 123")
        self.assertEqual(invoice.exchange_rate, 1.0)
        # "Fecha" (datetime) truncated to just its date part.
        self.assertEqual(invoice.invoice_date, date(2026, 9, 1))
        # "Fecha_Transaccion" (bare date) padded to a full datetime.
        self.assertEqual(invoice.transaction_date, datetime(2026, 9, 1, 0, 0, 0))
        self.assertEqual(invoice.due_date_1, date(2026, 9, 15))
        # MySQL zero-date placeholder becomes an empty field, not a
        # parse error.
        self.assertFalse(invoice.due_date_2)
        # Trailing ';' stripped from "Comp_Pago".
        self.assertEqual(invoice.associated_receipt_number, "0001-00000456")
        self.assertEqual(invoice.cae, "86349888860306")
        self.assertEqual(invoice.cae_due_date, date(2026, 9, 11))
        # "Detalle" parsed into real line records, in order, negative
        # amounts (discounts) kept as-is.
        self.assertEqual(len(invoice.line_ids), 2)
        first, second = invoice.line_ids
        self.assertEqual(first.article_code, "1")
        self.assertEqual(first.description, "Internet 20MB")
        self.assertEqual(first.amount_untaxed, 1000.00)
        self.assertEqual(first.tax_percent, 21.00)
        self.assertEqual(first.amount_total, 1210.00)
        self.assertEqual(second.article_code, "2")
        self.assertEqual(second.description, "WiFi Router")
        self.assertEqual(second.amount_untaxed, -100.00)
        self.assertEqual(second.amount_total, -121.00)

    def test_import_new_receipt_creates_pending(self):
        self._mock_client(receipt_rows=[SAMPLE_RECEIPT_ROW])
        self.company.action_phantom_import()

        receipt = self.env["phantom.receipt"].search([("phantom_idt", "=", "2001")])
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.state, "pending")
        self.assertEqual(receipt.payment_method, "Transferencia")
        self.assertEqual(receipt.address, "Calle Falsa 123")
        self.assertEqual(receipt.receipt_date, date(2026, 9, 1))
        self.assertEqual(receipt.transaction_date, datetime(2026, 9, 1, 0, 0, 0))

    def test_reimport_same_idt_updates_not_duplicates(self):
        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.action_phantom_import()

        updated_row = dict(SAMPLE_INVOICE_ROW, RS="Acme SA Updated")
        self._mock_client(invoice_rows=[updated_row])
        self.company.action_phantom_import()

        invoices = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.partner_name, "Acme SA Updated")
        # Lines are replaced on re-import, not accumulated.
        self.assertEqual(len(invoices.line_ids), 2)

    def test_import_unparseable_detail_creates_fallback_line(self):
        malformed_row = dict(SAMPLE_INVOICE_ROW, Detalle="not a valid detail string")
        self._mock_client(invoice_rows=[malformed_row])
        self.company.action_phantom_import()

        invoice = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        self.assertEqual(len(invoice.line_ids), 1)
        line = invoice.line_ids
        self.assertEqual(line.description, "not a valid detail string")
        self.assertEqual(line.amount_untaxed, 1000.00)
        self.assertEqual(line.amount_total, 1210.00)

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
            "odoo.addons.phantom_connector.models.phantom_api_client.requests.post"
        ) as mock_post:
            self.env["res.company"]._cron_phantom_import()
            mock_post.assert_not_called()

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

    def test_group_phantom_user_can_trigger_import(self):
        """group_phantom_user has neither read access to phantom_password
        nor write access to res.company/phantom.invoice/phantom.receipt,
        but can still trigger a manual import -- the underlying
        read/write operations run under sudo() (see
        ResCompany._phantom_import_one), gated by an explicit group
        check in action_phantom_import() rather than by direct ACLs.
        """
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom User",
            "login": "phantom_user_import_test",
            "email": "phantom_user_import_test@example.com",
            "group_ids": [Command.link(self.env.ref("phantom_connector.group_phantom_user").id)],
        })
        self._mock_client(invoice_rows=[SAMPLE_INVOICE_ROW])
        self.company.with_user(user).action_phantom_import()

        invoice = self.env["phantom.invoice"].search([("phantom_idt", "=", "1001")])
        self.assertEqual(len(invoice), 1)

    def test_user_without_phantom_group_cannot_trigger_import(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "No Phantom Access",
            "login": "no_phantom_access_test",
            "email": "no_phantom_access_test@example.com",
        })
        with self.assertRaises(AccessError):
            self.company.with_user(user).action_phantom_import()
