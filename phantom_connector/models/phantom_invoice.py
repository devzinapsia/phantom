from odoo import Command, _, fields, models

# Phantom "Tipo" -> short prefix for the display name, matching how a real
# Odoo document shows its number (e.g. "FA-B 0001-00000123"). Display-only:
# unrelated to phantom_account_bridge's own move_type/document_type mapping.
_DOC_TYPE_PREFIXES = {"Factura": "FA", "NC": "NC", "ND": "ND"}


class PhantomInvoice(models.Model):
    """Raw, one-to-one copy of a Phantom 'Consultar_Transacciones_Facturacion'
    row (invoices, credit notes and debit notes). Nothing here is
    transformed into a real accounting document -- that is the job of
    phantom_account_bridge, if installed.
    """

    _name = "phantom.invoice"
    _description = "Phantom Invoice (staging)"
    _inherit = ["phantom.staging.mixin"]
    _order = "transaction_date desc, id desc"

    phantom_idt = fields.Char(string="Phantom transaction ID", required=True, index=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company, index=True,
    )
    doc_type = fields.Char(string="Document type", help="Phantom 'Tipo': Factura, NC or ND.")
    comp_letter = fields.Char(string="Voucher letter", help="Phantom 'Tipo_Comp' (A, B, C).")
    point_of_sale = fields.Char(string="Point of sale")
    comp_number = fields.Char(string="Voucher number", index=True)
    invoice_date = fields.Date(string="Voucher date")
    transaction_date = fields.Datetime(string="Transaction date")
    phantom_customer_id = fields.Char(string="Phantom customer ID", index=True)
    partner_name = fields.Char(string="Customer name")
    customer_doc_type = fields.Char(string="Customer document type")
    customer_document = fields.Char(string="Customer document number")
    address = fields.Char(string="Address")
    city = fields.Char(string="City")
    currency_code = fields.Char(string="Currency code", help="PES or USD, as reported by Phantom.")
    exchange_rate = fields.Float(string="Exchange rate")
    detail_raw = fields.Text(
        string="Detail (raw)",
        help="Phantom 'Detalle', kept as-is: 'ID_ART, DESCRIPTION, NET, %TAX, "
        "TOTAL;' repeated per item, separated by ';'.",
    )
    amount_untaxed = fields.Float(string="Untaxed amount")
    amount_tax = fields.Float(string="Tax amount")
    amount_total = fields.Float(string="Total amount")
    due_date_1 = fields.Date(string="First due date")
    due_date_2 = fields.Date(string="Second due date")
    cae = fields.Char(
        string="CAE",
        help="AFIP electronic authorization code ('CAE'), as already issued "
        "to Phantom by AFIP -- Odoo never requests it, only records it.",
    )
    cae_due_date = fields.Date(string="CAE due date", help="Phantom 'CAE_Vto'.")
    associated_receipt_number = fields.Char(
        string="Associated receipt number",
        help="Phantom 'Comp_Pago' (the generic manual calls this field "
        "'Comp_Asociado', but real API responses use 'Comp_Pago'): set "
        "only when the payment was imputed to this voucher rather than "
        "left on account. Kept as raw text -- seen with a trailing ';' "
        "and what looks like a point-of-sale prefix (e.g. '21-00045210;'), "
        "not yet confirmed to always be a single simple value.",
    )
    branch_id_phantom = fields.Char(string="Phantom branch ID")
    state = fields.Selection(
        [("pending", "Pending"), ("processed", "Processed"), ("error", "Error")],
        string="Status", default="pending", required=True, index=True,
    )
    error_message = fields.Text(string="Error message")
    line_ids = fields.One2many(
        "phantom.invoice.line", "invoice_id", string="Lines",
        help="Parsed from Phantom's 'Detalle' at import time.",
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer", readonly=True, copy=False,
        help="Set by phantom_account_bridge once this invoice is processed "
        "into a real account.move -- empty for a still-pending invoice, "
        "since phantom_connector on its own never creates or links partner "
        "records (see phantom_staging_mixin.py in phantom_account_bridge).",
    )

    _phantom_idt_company_uniq = models.Constraint(
        "unique(phantom_idt, company_id)",
        "A Phantom invoice with this transaction ID already exists for this company.",
    )

    def _compute_display_name(self):
        for invoice in self:
            prefix = _DOC_TYPE_PREFIXES.get(invoice.doc_type, invoice.doc_type or "")
            header = "-".join(part for part in (prefix, invoice.comp_letter) if part)
            point_of_sale = (invoice.point_of_sale or "").zfill(4)
            comp_number = (invoice.comp_number or "").zfill(8)
            number = f"{point_of_sale}-{comp_number}"
            invoice.display_name = f"{header} {number}".strip() if header else number

    @staticmethod
    def _phantom_parse_detail_lines(detail_raw, amount_untaxed=0.0, amount_tax=0.0):
        """Parse Phantom's 'Detalle': 'ID_ART, DESCRIPTION, NET, %TAX,
        TOTAL;' repeated per item, separated by ';'. Returns a list of vals
        dicts for phantom.invoice.line.

        Confirmed against ~8000 real invoices: multi-item Detalle is the
        common case (not the exception -- ~99% of real rows have more than
        one item), amounts can be negative (discounts/bonificaciones), tax
        percent can come with varying decimal precision, and article
        code/description can both be empty for some items. A description
        is allowed to contain literal commas: only the first field (article
        code) and the last three (net/tax%/total) are fixed-position,
        everything in between is rejoined as the description.

        Falls back to a single line built from the header's own totals if
        the text can't be parsed into any usable item (e.g. unexpected
        format), so a malformed Detalle never leaves the Lines tab empty.
        """
        items = []
        for sequence, chunk in enumerate((detail_raw or "").split(";"), start=1):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = [part.strip() for part in chunk.split(",")]
            if len(parts) < 5:
                continue
            article_code, total = parts[0], parts[-1]
            net, tax_pct = parts[-3], parts[-2]
            description = ",".join(parts[1:-3]).strip()
            try:
                net_amount = float(net)
                tax_percent = float(tax_pct)
                total_amount = float(total)
            except ValueError:
                continue
            items.append({
                "sequence": sequence * 10,
                "article_code": article_code or False,
                "description": description or article_code or False,
                "amount_untaxed": net_amount,
                "tax_percent": tax_percent,
                "amount_total": total_amount,
            })
        if not items:
            items.append({
                "sequence": 10,
                "article_code": False,
                "description": detail_raw or _("Phantom invoice"),
                "amount_untaxed": amount_untaxed,
                "tax_percent": (
                    round(amount_tax / amount_untaxed * 100, 2) if amount_untaxed else 0.0
                ),
                "amount_total": amount_untaxed + amount_tax,
            })
        return items

    def _phantom_vals_from_row(self, row):
        # Field names below are confirmed against real API responses, not
        # just the generic PDF manual, which disagrees with the live
        # server on several of them (documented per-field below).
        comp_pago = (row.get("Comp_Pago") or row.get("Comp_Asociado") or "").rstrip(";") or False
        return {
            "doc_type": row.get("Tipo") or False,
            "comp_letter": row.get("Tipo_Comp") or False,
            # Manual says "P_venta"; the real API uses "P_Venta".
            "point_of_sale": row.get("P_Venta") or row.get("P_venta") or False,
            "comp_number": row.get("Nro_Comp") or False,
            # "Fecha" comes back as a full datetime (e.g. "2026-09-01
            # 10:02:14") even though it maps to a Date field here.
            "invoice_date": self._phantom_clean_date(row.get("Fecha")),
            # "Fecha_Transaccion" comes back as a bare date (no time
            # component) even though it maps to a Datetime field here.
            "transaction_date": self._phantom_clean_datetime(row.get("Fecha_Transaccion")),
            "phantom_customer_id": row.get("IDA") or False,
            "partner_name": row.get("RS") or False,
            "customer_doc_type": row.get("Doc_Tipo") or False,
            "customer_document": row.get("Documento") or False,
            # Manual says "Dirección"; the real API uses "Direccion" (no accent).
            "address": row.get("Direccion") or row.get("Dirección") or False,
            "city": row.get("Ciudad") or False,
            "currency_code": row.get("Moneda") or False,
            # Manual says "Cotización"; the real API uses "Cotizacion" (no accent).
            "exchange_rate": row.get("Cotizacion") or row.get("Cotización") or 0.0,
            "detail_raw": row.get("Detalle") or False,
            "amount_untaxed": row.get("Importe_Neto") or 0.0,
            "amount_tax": row.get("Importe_IVA") or 0.0,
            "amount_total": row.get("Importe_Total") or 0.0,
            "line_ids": [Command.clear()] + [
                Command.create(vals) for vals in self._phantom_parse_detail_lines(
                    row.get("Detalle"),
                    row.get("Importe_Neto") or 0.0,
                    row.get("Importe_IVA") or 0.0,
                )
            ],
            # Phantom uses MySQL's zero-date ("0000-00-00") for an unset
            # due date; _phantom_clean_date turns that into False.
            "due_date_1": self._phantom_clean_date(row.get("Primer_Vto")),
            "due_date_2": self._phantom_clean_date(
                row.get("Segundo_Vto") or row.get("Segundo_Vtol")
            ),
            "cae": row.get("CAE") or False,
            "cae_due_date": self._phantom_clean_date(row.get("CAE_Vto")),
            # Manual calls this "Comp_Asociado"; the real API uses
            # "Comp_Pago" -- see the field's own help text.
            "associated_receipt_number": comp_pago,
            "branch_id_phantom": row.get("Suc_ID") or False,
        }
