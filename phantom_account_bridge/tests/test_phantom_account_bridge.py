import time

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

SAMPLE_INVOICE_ROW = {
    "Tipo": "Factura",
    "Tipo_Comp": "A",
    "P_venta": "0001",
    "Nro_Comp": "00000123",
    "Fecha": "2026-09-01",
    "Fecha_Transaccion": "2026-09-01 10:00:00",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30714295698",
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
    "Nro_Comp": "REC-0001",
    "Fecha": "2026-09-01",
    "Fecha_Transaccion": "2026-09-01 11:00:00",
    "IDA": "555",
    "RS": "Acme SA",
    "Doc_Tipo": "80",
    "Documento": "30714295698",
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


class TestPhantomAccountBridge(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_chart_template("ar_ri")
    def setUpClass(cls):
        super().setUpClass()

        # The default test company's chart of accounts is not Argentine, and
        # AccountTestInvoicingCommon.setUpClass() never applies
        # cls.chart_template to it (that only happens for companies created
        # via cls._create_company(), same as l10n_ar's own test suite does
        # for its secondary companies) -- so a dedicated AR company is
        # created here instead of reusing cls.company_data['company'].
        cls.company = cls._create_company(
            name="Phantom AR Test Co",
            country_id=cls.env.ref("base.ar").id,
        )
        cls.env.user.write({
            "company_ids": [Command.link(cls.company.id)],
            "company_id": cls.company.id,
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.company_data = cls.collect_company_accounting_data(cls.company)

        cls.company.write({
            "l10n_ar_afip_start_date": time.strftime("%Y-01-01"),
        })
        cls.company.partner_id.write({
            "l10n_latam_identification_type_id": cls.env.ref("l10n_ar.it_cuit").id,
            "vat": "30111111118",
            "country_id": cls.env.ref("base.ar").id,
        })
        cls.sale_journal = cls.company_data["default_journal_sale"]
        cls.receipt_journal = cls.company_data["default_journal_bank"]
        cls.classification = cls.env["account.move.classification"].create({
            "name": "Phantom",
        })
        cls.company.write({
            "phantom_enabled": True,
            "phantom_url": "http://phantom.example/api",
            "phantom_user": "api_user",
            "phantom_password": "api_pass",
            "phantom_sales_journal_id": cls.sale_journal.id,
            "phantom_receipt_journal_id": cls.receipt_journal.id,
            "phantom_default_product_id": cls.product.id,
            "phantom_classification_id": cls.classification.id,
        })

    def _create_invoice_staging(self, **overrides):
        row = dict(SAMPLE_INVOICE_ROW, **overrides)
        row.setdefault("IDT", row["Nro_Comp"])
        self.env["phantom.invoice"]._phantom_upsert([row], self.company)
        return self.env["phantom.invoice"].search([("phantom_idt", "=", row["IDT"])])

    def _create_receipt_staging(self, **overrides):
        row = dict(SAMPLE_RECEIPT_ROW, **overrides)
        row.setdefault("IDT", row["Nro_Comp"])
        self.env["phantom.receipt"]._phantom_upsert([row], self.company)
        return self.env["phantom.receipt"].search([("phantom_idt", "=", row["IDT"])])

    def test_invoice_creates_account_move(self):
        staging = self._create_invoice_staging(IDT="I1", Nro_Comp="00000123")
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        self.assertEqual(staging.state, "processed")
        move = staging.account_move_id
        self.assertTrue(move)
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.partner_id.vat, "30714295698")
        self.assertEqual(move.classification_id, self.classification)
        self.assertAlmostEqual(move.amount_untaxed, 1000.00)
        self.assertAlmostEqual(move.amount_tax, 210.00)

    def test_new_customer_created_and_reused_without_overwrite(self):
        staging1 = self._create_invoice_staging(IDT="I2", Nro_Comp="00000124")
        self.company._phantom_create_one()
        staging1.invalidate_recordset()
        partner = staging1.account_move_id.partner_id

        # Simulate a manual edit in Odoo that a later import must not undo.
        partner.write({"phone": "+54 111 000 0000"})

        staging2 = self._create_invoice_staging(
            IDT="I3", Nro_Comp="00000125", RS="Acme SA (renamed in Phantom)"
        )
        self.company._phantom_create_one()
        staging2.invalidate_recordset()

        self.assertEqual(staging2.account_move_id.partner_id, partner)
        self.assertEqual(partner.phone, "+54 111 000 0000")
        self.assertEqual(partner.name, "Acme SA")

    def test_receipt_creates_account_payment(self):
        staging = self._create_receipt_staging(IDT="R1", Nro_Comp="REC-0010")
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        self.assertEqual(staging.state, "processed")
        payment = staging.account_payment_id
        self.assertTrue(payment)
        self.assertEqual(payment.move_id.state, "posted")
        self.assertAlmostEqual(payment.amount, 1210.00)

    def test_reconcile_invoice_with_already_processed_receipt(self):
        self._create_receipt_staging(IDT="R2", Nro_Comp="REC-0020")
        self.company._phantom_create_one()

        invoice_staging = self._create_invoice_staging(
            IDT="I4", Nro_Comp="00000126", Comp_Asociado="REC-0020"
        )
        self.company._phantom_create_one()
        invoice_staging.invalidate_recordset()

        self.assertFalse(invoice_staging.pending_reconciliation)
        receivable_line = invoice_staging.account_move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable"
        )
        self.assertTrue(receivable_line.reconciled)

    def test_invoice_with_not_yet_processed_receipt_marks_pending(self):
        invoice_staging = self._create_invoice_staging(
            IDT="I5", Nro_Comp="00000127", Comp_Asociado="REC-0030"
        )
        self.company._phantom_create_one()
        invoice_staging.invalidate_recordset()

        self.assertEqual(invoice_staging.state, "processed")
        self.assertTrue(invoice_staging.pending_reconciliation)

        self._create_receipt_staging(IDT="R3", Nro_Comp="REC-0030")
        self.company._phantom_create_one()
        invoice_staging.invalidate_recordset()

        self.assertFalse(invoice_staging.pending_reconciliation)
        receivable_line = invoice_staging.account_move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable"
        )
        self.assertTrue(receivable_line.reconciled)

    def test_receipt_without_invoice_left_unreconciled(self):
        staging = self._create_receipt_staging(IDT="R4", Nro_Comp="REC-0040")
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        self.assertEqual(staging.state, "processed")
        receivable_line = staging.account_payment_id.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable"
        )
        self.assertFalse(receivable_line.reconciled)

    def test_error_on_one_record_does_not_block_batch(self):
        bad = self._create_invoice_staging(IDT="I6", Nro_Comp="00000128", Tipo="Unknown")
        good = self._create_invoice_staging(IDT="I7", Nro_Comp="00000129")
        self.company._phantom_create_one()
        bad.invalidate_recordset()
        good.invalidate_recordset()

        self.assertEqual(bad.state, "error")
        self.assertTrue(bad.error_message)
        self.assertEqual(good.state, "processed")

    def test_smart_buttons_link_to_correct_document(self):
        staging = self._create_invoice_staging(IDT="I8", Nro_Comp="00000130")
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        invoice_action = staging.action_view_account_move()
        self.assertEqual(invoice_action["res_id"], staging.account_move_id.id)

        move_action = staging.account_move_id.action_view_phantom_invoice()
        self.assertEqual(move_action["res_id"], staging.id)
