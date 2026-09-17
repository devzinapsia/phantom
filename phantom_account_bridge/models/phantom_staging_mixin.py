from odoo import _, models
from odoo.exceptions import UserError


class PhantomStagingMixin(models.AbstractModel):
    """Adds customer matching, shared by phantom.invoice and phantom.receipt
    (both already inherit phantom.staging.mixin from phantom_connector, and
    share the same customer fields: phantom_customer_id, partner_name,
    customer_doc_type, customer_document, address, city).

    Matching is done by identification (customer_doc_type -> AFIP code ->
    l10n_latam.identification.type, customer_document -> res.partner.vat),
    never by Phantom's own IDA: res.partner is never extended with a
    Phantom-specific field, by design -- traceability instead flows
    partner -> account.move/account.payment -> phantom.invoice/receipt.
    """

    _inherit = "phantom.staging.mixin"

    def _phantom_get_identification_type(self):
        self.ensure_one()
        if not self.customer_doc_type:
            return self.env["l10n_latam.identification.type"]
        identification_type = self.env["l10n_latam.identification.type"].search([
            ("l10n_ar_afip_code", "=", self.customer_doc_type),
            ("country_id.code", "=", "AR"),
        ], limit=1)
        if not identification_type:
            raise UserError(
                _(
                    "No identification type found for Phantom document type code "
                    "'%(doc_type)s'.",
                    doc_type=self.customer_doc_type,
                )
            )
        return identification_type

    def _phantom_get_or_create_partner(self, company):
        self.ensure_one()
        identification_type = self._phantom_get_identification_type()
        vat = self.customer_document or False

        if identification_type and vat:
            partner = self.env["res.partner"].search([
                ("l10n_latam_identification_type_id", "=", identification_type.id),
                ("vat", "=", vat),
                "|", ("company_id", "=", False), ("company_id", "=", company.id),
            ], limit=1)
            if partner:
                return partner

        return self.env["res.partner"].create({
            "name": self.partner_name or vat or _("Unknown Phantom customer"),
            "l10n_latam_identification_type_id": identification_type.id or False,
            "vat": vat,
            "street": self.address or False,
            "city": self.city or False,
        })
