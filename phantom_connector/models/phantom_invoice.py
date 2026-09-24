from odoo import fields, models


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

    _phantom_idt_company_uniq = models.Constraint(
        "unique(phantom_idt, company_id)",
        "A Phantom invoice with this transaction ID already exists for this company.",
    )

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
            # Phantom uses MySQL's zero-date ("0000-00-00") for an unset
            # due date; _phantom_clean_date turns that into False.
            "due_date_1": self._phantom_clean_date(row.get("Primer_Vto")),
            "due_date_2": self._phantom_clean_date(
                row.get("Segundo_Vto") or row.get("Segundo_Vtol")
            ),
            # Manual calls this "Comp_Asociado"; the real API uses
            # "Comp_Pago" -- see the field's own help text.
            "associated_receipt_number": comp_pago,
            "branch_id_phantom": row.get("Suc_ID") or False,
        }
