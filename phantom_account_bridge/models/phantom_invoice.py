from odoo import Command, _, fields, models
from odoo.exceptions import UserError

# Phantom "Tipo" -> (account.move move_type, l10n_latam.document.type internal_type).
# "ND" (debit note) has no dedicated move_type in Odoo/AR: it is an
# 'out_invoice' like "Factura", distinguished only by its document type's
# internal_type ('debit_note' vs 'invoice'). Confirmed against
# l10n_latam_invoice_document/models/l10n_latam_document_type.py.
_DOC_TYPE_MAP = {
    "Factura": ("out_invoice", "invoice"),
    "ND": ("out_invoice", "debit_note"),
    "NC": ("out_refund", "credit_note"),
}


class PhantomInvoice(models.Model):
    _inherit = "phantom.invoice"

    account_move_id = fields.Many2one(
        "account.move", string="Invoice", readonly=True, copy=False
    )
    pending_reconciliation = fields.Boolean(
        default=False, copy=False,
        help="Set when this invoice has an associated receipt number but "
        "that receipt wasn't processed into a real payment yet. Retried "
        "on every creation run until it can be reconciled.",
    )

    def action_view_account_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.account_move_id.id,
        }

    def _phantom_create_document(self, company):
        self.ensure_one()
        partner = self._phantom_get_or_create_partner(company)
        move_type, document_type = self._phantom_get_move_type_and_document()

        move = self.env["account.move"].create({
            "move_type": move_type,
            "l10n_latam_document_type_id": document_type.id,
            "partner_id": partner.id,
            "company_id": company.id,
            "journal_id": company.phantom_sales_journal_id.id,
            "invoice_date": self.invoice_date,
            "classification_id": company.phantom_classification_id.id,
            "invoice_line_ids": self._phantom_invoice_line_vals(company),
            **self._phantom_cae_vals(),
        })
        move.action_post()
        self.write({"account_move_id": move.id, "partner_id": partner.id, "state": "processed"})
        self._phantom_try_reconcile(company)
        return move

    def _phantom_get_move_type_and_document(self):
        self.ensure_one()
        mapped = _DOC_TYPE_MAP.get(self.doc_type)
        if not mapped:
            raise UserError(
                _("Unknown Phantom document type '%(doc_type)s'.", doc_type=self.doc_type)
            )
        move_type, internal_type = mapped
        document_type = self.env["l10n_latam.document.type"].search([
            ("country_id.code", "=", "AR"),
            ("internal_type", "=", internal_type),
            ("l10n_ar_letter", "=", self.comp_letter),
        ], limit=1)
        if not document_type:
            raise UserError(
                _(
                    "No document type found for letter '%(letter)s' and type "
                    "'%(doc_type)s'.",
                    letter=self.comp_letter, doc_type=self.doc_type,
                )
            )
        return move_type, document_type

    def _phantom_cae_vals(self):
        """account.move vals recording the CAE Phantom already obtained from
        AFIP -- Odoo never requests one itself here, only records it, same
        pattern already used by l10n_ar_import_bill's manual AFIP import
        wizard and l10n_ar_wsmtxca_ws (both confirmed in grupolara's actual
        installed ingadhoc modules, not guessed): l10n_ar_afip_auth_code,
        l10n_ar_afip_auth_code_due, l10n_ar_afip_auth_mode="CAE".
        """
        self.ensure_one()
        if not self.cae:
            return {}
        return {
            "l10n_ar_afip_auth_code": self.cae,
            "l10n_ar_afip_auth_code_due": self.cae_due_date,
            "l10n_ar_afip_auth_mode": "CAE",
        }

    def _phantom_invoice_line_vals(self, company):
        """Build account.move.line vals from this invoice's own line_ids,
        already parsed from Phantom's 'Detalle' at import time by
        phantom_connector (see phantom.invoice._phantom_parse_detail_lines)
        -- not re-parsed here, so there is a single source of truth for
        the parsing logic.
        """
        self.ensure_one()
        analytic_distribution = (
            {str(company.phantom_analytic_account_id.id): 100.0}
            if company.phantom_analytic_account_id else False
        )
        return [
            Command.create({
                "product_id": company.phantom_default_product_id.id,
                "name": line.description or line.article_code,
                "quantity": 1,
                "price_unit": line.amount_untaxed,
                "tax_ids": [
                    Command.set(self._phantom_get_sale_tax(company, line.tax_percent).ids)
                ],
                "analytic_distribution": analytic_distribution,
            })
            for line in self.line_ids
        ]

    def _phantom_get_sale_tax(self, company, tax_percent):
        self.ensure_one()
        tax = self.env["account.tax"].search([
            ("company_id", "=", company.id),
            ("type_tax_use", "=", "sale"),
            ("amount_type", "=", "percent"),
            ("amount", "=", tax_percent),
        ], limit=1)
        if not tax:
            raise UserError(
                _(
                    "No sale tax found for %(tax_percent)s%% in company "
                    "%(company)s.",
                    tax_percent=tax_percent, company=company.name,
                )
            )
        return tax

    def _phantom_try_reconcile(self, company):
        """Reconcile this invoice against its associated receipt's payment,
        if that receipt has already been processed. Idempotent: safe to
        call again on a retry pass, and leaves pending_reconciliation set
        when the receipt still isn't ready.
        """
        self.ensure_one()
        if not self.associated_receipt_number or not self.account_move_id:
            self.pending_reconciliation = False
            return
        receipt = self.env["phantom.receipt"].search([
            ("comp_number", "=", self.associated_receipt_number),
            ("company_id", "=", company.id),
        ], limit=1)
        if not receipt or not receipt.account_payment_id:
            self.pending_reconciliation = True
            return
        self._phantom_reconcile_with_payment(receipt.account_payment_id)
        self.pending_reconciliation = False

    def _phantom_reconcile_with_payment(self, payment):
        self.ensure_one()
        invoice_line = self.account_move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        )
        payment_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        )
        if invoice_line and payment_line:
            (invoice_line + payment_line).reconcile()
