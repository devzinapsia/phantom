from odoo import fields, models


class PhantomReceipt(models.Model):
    """Raw, one-to-one copy of a Phantom 'Consultar_Transacciones_Pagos'
    row (payment receipts). Nothing here is transformed into a real
    accounting document -- that is the job of phantom_account_bridge, if
    installed.
    """

    _name = "phantom.receipt"
    _description = "Phantom Receipt (staging)"
    _inherit = ["phantom.staging.mixin"]
    _order = "transaction_date desc, id desc"

    phantom_idt = fields.Char(string="Phantom transaction ID", required=True, index=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company, index=True,
    )
    comp_number = fields.Char(string="Voucher number", index=True)
    receipt_date = fields.Date(string="Voucher date")
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
        help="Phantom 'Detalle', kept as-is. May contain the literal "
        "'Pago Parcial de Comprobante' notice for an open/partial payment.",
    )
    amount_total = fields.Float(string="Total amount")
    payment_method = fields.Char(string="Payment method")
    reference = fields.Char(string="Reference")
    branch_id_phantom = fields.Char(string="Phantom branch ID")
    state = fields.Selection(
        [("pending", "Pending"), ("processed", "Processed"), ("error", "Error")],
        string="Status", default="pending", required=True, index=True,
    )
    error_message = fields.Text(string="Error message")
    partner_id = fields.Many2one(
        "res.partner", string="Customer", readonly=True, copy=False,
        help="Set by phantom_account_bridge once this receipt is processed "
        "into a real account.payment -- empty for a still-pending receipt, "
        "since phantom_connector on its own never creates or links partner "
        "records (see phantom_staging_mixin.py in phantom_account_bridge).",
    )

    _phantom_idt_company_uniq = models.Constraint(
        "unique(phantom_idt, company_id)",
        "A Phantom receipt with this transaction ID already exists for this company.",
    )

    def _compute_display_name(self):
        for receipt in self:
            receipt.display_name = (receipt.comp_number or "").zfill(8)

    def _phantom_vals_from_row(self, row):
        # Field names below are confirmed against real API responses, not
        # just the generic PDF manual, which disagrees with the live
        # server on several of them (documented per-field below).
        return {
            "comp_number": row.get("Nro_Comp") or False,
            # "Fecha" comes back as a full datetime even though it maps
            # to a Date field here.
            "receipt_date": self._phantom_clean_date(row.get("Fecha")),
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
            "amount_total": row.get("Importe_Total") or 0.0,
            "payment_method": row.get("Medio_Pago") or False,
            "reference": row.get("Referencia") or False,
            "branch_id_phantom": row.get("Suc_ID") or False,
        }
