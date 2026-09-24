import time
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError

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
    "CAE": "86349888860306",
    "CAE_Vto": "2026-09-11",
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
            "group_ids": [Command.link(cls.env.ref("phantom_connector.group_phantom_manager").id)],
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
        # sudo(): phantom_password is restricted to group_phantom_manager,
        # which this test's default company-admin user isn't a member of.
        cls.company.sudo().write({
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

    def _mock_message_notify(self):
        # patch.object on the *runtime* class (type(self.env["mail.thread"])),
        # not a static "odoo.addons.mail.models.mail_thread.MailThread"
        # import path -- Odoo composes a fresh class per model at registry
        # build time, so patching the raw imported class silently misses
        # the one actually used by self.env["mail.thread"].
        return patch.object(type(self.env["mail.thread"]), "message_notify")

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
        # Letter "A" -> CUIT + Responsable Inscripto.
        self.assertEqual(
            move.partner_id.l10n_latam_identification_type_id, self.env.ref("l10n_ar.it_cuit")
        )
        self.assertEqual(
            move.partner_id.l10n_ar_afip_responsibility_type_id, self.env.ref("l10n_ar.res_IVARI")
        )
        self.assertEqual(move.partner_id.state_id, self.env.ref("base.state_ar_b"))
        self.assertEqual(move.partner_id.country_id, self.env.ref("base.ar"))
        self.assertIn("555", move.partner_id.comment or "")
        # CAE, already obtained by Phantom from AFIP, recorded as-is.
        self.assertEqual(move.l10n_ar_afip_auth_code, "86349888860306")
        self.assertEqual(move.l10n_ar_afip_auth_code_due, date(2026, 9, 11))
        self.assertEqual(move.l10n_ar_afip_auth_mode, "CAE")

    def test_letter_b_sets_consumidor_final_and_dni(self):
        staging = self._create_invoice_staging(
            IDT="I9", Nro_Comp="00000131", Tipo_Comp="B", Doc_Tipo="96", Documento="12345678",
        )
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        partner = staging.account_move_id.partner_id
        self.assertEqual(partner.l10n_latam_identification_type_id, self.env.ref("l10n_ar.it_dni"))
        self.assertEqual(partner.l10n_ar_afip_responsibility_type_id, self.env.ref("l10n_ar.res_CF"))
        self.assertEqual(partner.vat, "12345678")

    def test_missing_cae_leaves_afip_fields_empty(self):
        staging = self._create_invoice_staging(
            IDT="I14", Nro_Comp="00000136", CAE="", CAE_Vto="",
        )
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        move = staging.account_move_id
        self.assertFalse(move.l10n_ar_afip_auth_code)
        self.assertFalse(move.l10n_ar_afip_auth_mode)

    def test_customer_matched_by_phantom_id_in_notes(self):
        staging1 = self._create_invoice_staging(IDT="I10", Nro_Comp="00000132")
        self.company._phantom_create_one()
        staging1.invalidate_recordset()
        partner = staging1.account_move_id.partner_id

        # Same Phantom customer (IDA "555", unchanged), but a different
        # document this time -- must still match the existing partner via
        # the Phantom ID note, not create a duplicate.
        staging2 = self._create_invoice_staging(
            IDT="I11", Nro_Comp="00000133", Documento="99999999999",
        )
        self.company._phantom_create_one()
        staging2.invalidate_recordset()

        self.assertEqual(staging2.account_move_id.partner_id, partner)

    def test_customer_matched_by_name_fallback(self):
        staging1 = self._create_invoice_staging(IDT="I12", Nro_Comp="00000134")
        self.company._phantom_create_one()
        staging1.invalidate_recordset()
        partner = staging1.account_move_id.partner_id

        # Different Phantom customer ID and document, but the same name
        # ("Acme SA", unchanged) -- must still match by name as a last
        # resort.
        staging2 = self._create_invoice_staging(
            IDT="I13", Nro_Comp="00000135", IDA="999", Documento="11111111111",
        )
        self.company._phantom_create_one()
        staging2.invalidate_recordset()

        self.assertEqual(staging2.account_move_id.partner_id, partner)

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

    def test_group_phantom_user_can_trigger_create(self):
        """group_phantom_user has none of the real accounting/partner
        create rights _phantom_create_one actually needs, but can still
        trigger it via action_phantom_create() -- gated by an explicit
        group check rather than by direct ACLs, same pattern as
        action_phantom_import in phantom_connector.
        """
        staging = self._create_invoice_staging(IDT="I15", Nro_Comp="00000137")
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom User",
            "login": "phantom_user_create_test",
            "email": "phantom_user_create_test@example.com",
            "company_ids": [Command.link(self.company.id)],
            "company_id": self.company.id,
            "group_ids": [Command.link(self.env.ref("phantom_connector.group_phantom_user").id)],
        })
        self.company.with_user(user).action_phantom_create()
        staging.invalidate_recordset()

        self.assertEqual(staging.state, "processed")
        self.assertTrue(staging.account_move_id)

    def test_user_without_phantom_group_cannot_trigger_create(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "No Phantom Access",
            "login": "no_phantom_access_create_test",
            "email": "no_phantom_access_create_test@example.com",
        })
        with self.assertRaises(AccessError):
            self.company.with_user(user).action_phantom_create()

    def test_batch_create_processes_in_chunks(self):
        stagings = [
            self._create_invoice_staging(IDT=f"I{100 + i}", Nro_Comp=f"0000013{8 + i}")
            for i in range(3)
        ]

        result = self.company.action_phantom_create_batch(batch_size=2)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["remaining"], 1)
        self.assertFalse(result["done"])
        for staging in stagings:
            staging.invalidate_recordset()
        self.assertEqual(sum(1 for s in stagings if s.state == "processed"), 2)

        result = self.company.action_phantom_create_batch(batch_size=2)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["remaining"], 0)
        self.assertTrue(result["done"])
        for staging in stagings:
            staging.invalidate_recordset()
        self.assertTrue(all(s.state == "processed" for s in stagings))
        self.assertTrue(self.company.phantom_last_creation_date)

    def test_invoice_sets_afip_service_period(self):
        """Service period (first/last day of the invoice's own month) is
        set before create(), avoiding ARCA's "Debe completar el período
        correspondiente a la facturación de servicios" error -- l10n_ar's
        own auto-fill for this (account.move._set_afip_service_dates())
        only runs after action_post()'s own super() call, too late to
        avoid a validation that happens earlier in the MRO.
        """
        staging = self._create_invoice_staging(IDT="I18", Nro_Comp="00000140")
        self.company._phantom_create_one()
        staging.invalidate_recordset()

        move = staging.account_move_id
        self.assertEqual(move.l10n_ar_afip_service_start, date(2026, 9, 1))
        self.assertEqual(move.l10n_ar_afip_service_end, date(2026, 9, 30))

    def test_error_record_is_retried_on_next_run(self):
        bad = self._create_invoice_staging(IDT="I17", Nro_Comp="00000139", Tipo="Unknown")
        self.company._phantom_create_one()
        bad.invalidate_recordset()
        self.assertEqual(bad.state, "error")

        # Simulate the underlying issue being fixed (e.g. a bad Tipo, or --
        # what actually happened in production -- a missing AFIP service
        # period, now handled automatically).
        bad.doc_type = "Factura"
        self.company._phantom_create_one()
        bad.invalidate_recordset()

        self.assertEqual(bad.state, "processed")
        self.assertTrue(bad.account_move_id)

    def test_notification_summary_sent_on_success(self):
        responsible = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom Responsible",
            "login": "phantom_responsible_test",
            "email": "phantom_responsible_test@example.com",
        })
        self.company.sudo().phantom_notify_user_ids = [Command.link(responsible.id)]
        self._create_invoice_staging(IDT="I19", Nro_Comp="00000141")

        with self._mock_message_notify() as mock_notify:
            self.company._phantom_create_one()

        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        self.assertIn(responsible.partner_id.id, kwargs["partner_ids"])
        self.assertIn("successfully", kwargs["subject"])
        self.assertIn("Invoices processed: 1", kwargs["body"])

    def test_notification_summary_reports_errors(self):
        responsible = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Phantom Responsible 2",
            "login": "phantom_responsible_test_2",
            "email": "phantom_responsible_test_2@example.com",
        })
        self.company.sudo().phantom_notify_user_ids = [Command.link(responsible.id)]
        self._create_invoice_staging(IDT="I21", Nro_Comp="00000143", Tipo="Unknown")

        with self._mock_message_notify() as mock_notify:
            self.company._phantom_create_one()

        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        self.assertIn("errors", kwargs["subject"])
        self.assertIn("errors: 1", kwargs["body"])

    def test_no_notification_without_responsible_users(self):
        self._create_invoice_staging(IDT="I20", Nro_Comp="00000142")
        with self._mock_message_notify() as mock_notify:
            self.company._phantom_create_one()
        mock_notify.assert_not_called()

    def test_invoice_and_receipt_log_creation_trigger_on_chatter(self):
        """Every account.move/account.payment created by Phantom gets a
        chatter note saying so, and whether this run was the automatic
        cron or a manual 'Process now' -- so anyone opening the document
        directly in Odoo (not the Phantom dashboard) can still see where
        it came from.
        """
        invoice_staging = self._create_invoice_staging(IDT="I22", Nro_Comp="00000144")
        receipt_staging = self._create_receipt_staging(IDT="I22", Nro_Comp="REC-0144")
        self.company._phantom_create_one(trigger="automatic")
        invoice_staging.invalidate_recordset()
        receipt_staging.invalidate_recordset()

        move_messages = invoice_staging.account_move_id.message_ids.mapped("body")
        self.assertTrue(any("automatic process" in body for body in move_messages))

        payment_messages = receipt_staging.account_payment_id.message_ids.mapped("body")
        self.assertTrue(any("automatic process" in body for body in payment_messages))

    def test_invoice_logs_manual_trigger_on_chatter(self):
        staging = self._create_invoice_staging(IDT="I23", Nro_Comp="00000145")
        self.company._phantom_create_one(trigger="manual")
        staging.invalidate_recordset()

        move_messages = staging.account_move_id.message_ids.mapped("body")
        self.assertTrue(any("manual process" in body for body in move_messages))
