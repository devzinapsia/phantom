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
        help="Phantom 'Comp_Asociado': set only when the payment was "
        "imputed to this voucher rather than left on account.",
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
        return {
            "doc_type": row.get("Tipo") or False,
            "comp_letter": row.get("Tipo_Comp") or False,
            "point_of_sale": row.get("P_venta") or False,
            "comp_number": row.get("Nro_Comp") or False,
            "invoice_date": row.get("Fecha") or False,
            "transaction_date": row.get("Fecha_Transaccion") or False,
            "phantom_customer_id": row.get("IDA") or False,
            "partner_name": row.get("RS") or False,
            "customer_doc_type": row.get("Doc_Tipo") or False,
            "customer_document": row.get("Documento") or False,
            "address": row.get("Dirección") or False,
            "city": row.get("Ciudad") or False,
            "currency_code": row.get("Moneda") or False,
            "exchange_rate": row.get("Cotización") or 0.0,
            "detail_raw": row.get("Detalle") or False,
            "amount_untaxed": row.get("Importe_Neto") or 0.0,
            "amount_tax": row.get("Importe_IVA") or 0.0,
            "amount_total": row.get("Importe_Total") or 0.0,
            "due_date_1": row.get("Primer_Vto") or False,
            # The Phantom manual lists this key as "Segundo_Vtol" (likely a
            # typo, since its counterpart above is "Primer_Vto"); accept
            # either spelling until this is confirmed against the real API.
            "due_date_2": row.get("Segundo_Vto") or row.get("Segundo_Vtol") or False,
            "associated_receipt_number": row.get("Comp_Asociado") or False,
            "branch_id_phantom": row.get("Suc_ID") or False,
        }
