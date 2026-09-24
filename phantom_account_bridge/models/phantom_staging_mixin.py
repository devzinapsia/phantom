from odoo import _, models
from odoo.exceptions import UserError

# A Phantom invoice's own letter already implies the customer's AFIP
# identification type and responsibility type, per AFIP rules: letter "A" is
# only ever issued to a Responsable Inscripto (who has a CUIT), letter "B" to
# a Consumidor Final / exempt customer (who has at most a DNI). Confirmed
# against real l10n_ar seed data, not assumed:
# l10n_ar/data/l10n_latam_identification_type_data.xml (it_cuit -> AFIP code
# 80, it_dni -> AFIP code 96) and
# l10n_ar/data/l10n_ar_afip_responsibility_type_data.xml (res_IVARI = "IVA
# Responsable Inscripto", res_CF = "Consumidor Final"). Only phantom.invoice
# has a comp_letter field -- phantom.receipt does not, so this mapping never
# applies there, and _phantom_get_identification_type falls back to the
# Doc_Tipo-based lookup below.
_LETTER_IDENTIFICATION_TYPE_XMLID = {
    "A": "l10n_ar.it_cuit",
    "B": "l10n_ar.it_dni",
}
_LETTER_RESPONSIBILITY_TYPE_XMLID = {
    "A": "l10n_ar.res_IVARI",
    "B": "l10n_ar.res_CF",
}


class PhantomStagingMixin(models.AbstractModel):
    """Adds customer matching, shared by phantom.invoice and phantom.receipt
    (both already inherit phantom.staging.mixin from phantom_connector, and
    share the same customer fields: phantom_customer_id, partner_name,
    customer_doc_type, customer_document, address, city).

    Matching tries, in order, the most reliable identifier first: CUIT/DNI
    (identification type + res.partner.vat), then Phantom's own customer ID
    (IDA, stored as a plain marker line in res.partner.comment -- Notes --
    since res.partner is deliberately never extended with a dedicated
    Phantom-specific field), then exact customer name as a last resort.
    Whichever matches first wins; none of these overwrite an existing
    partner's data. Traceability the other way (account.move/account.payment
    -> phantom.invoice/receipt) is unaffected by this.
    """

    _inherit = "phantom.staging.mixin"

    def _phantom_get_identification_type(self):
        self.ensure_one()
        letter_xmlid = _LETTER_IDENTIFICATION_TYPE_XMLID.get(getattr(self, "comp_letter", False))
        if letter_xmlid:
            return self.env.ref(letter_xmlid)
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

    def _phantom_get_responsibility_type(self):
        self.ensure_one()
        letter_xmlid = _LETTER_RESPONSIBILITY_TYPE_XMLID.get(getattr(self, "comp_letter", False))
        return self.env.ref(letter_xmlid) if letter_xmlid else self.env["l10n_ar.afip.responsibility.type"]

    def _phantom_customer_id_note(self):
        """Not translated on purpose: this marker is written into the
        partner's Notes at creation time and searched for again on every
        later match attempt, potentially under a different language context
        (e.g. a manual run under the logged-in user's language vs. the
        automatic cron running as OdooBot) -- translating it would make a
        partner created in one language unmatchable from another.
        """
        self.ensure_one()
        if not self.phantom_customer_id:
            return False
        return "Phantom customer ID: %s" % self.phantom_customer_id

    def _phantom_get_or_create_partner(self, company):
        self.ensure_one()
        identification_type = self._phantom_get_identification_type()
        vat = self.customer_document or False
        company_domain = ["|", ("company_id", "=", False), ("company_id", "=", company.id)]

        if identification_type and vat:
            partner = self.env["res.partner"].search([
                ("l10n_latam_identification_type_id", "=", identification_type.id),
                ("vat", "=", vat),
                *company_domain,
            ], limit=1)
            if partner:
                return partner

        note = self._phantom_customer_id_note()
        if note:
            partner = self.env["res.partner"].search([
                ("comment", "like", note),
                *company_domain,
            ], limit=1)
            if partner:
                return partner

        if self.partner_name:
            partner = self.env["res.partner"].search([
                ("name", "=", self.partner_name),
                *company_domain,
            ], limit=1)
            if partner:
                return partner

        return self.env["res.partner"].create({
            "name": self.partner_name or vat or _("Unknown Phantom customer"),
            "l10n_latam_identification_type_id": identification_type.id or False,
            "vat": vat,
            "l10n_ar_afip_responsibility_type_id": self._phantom_get_responsibility_type().id or False,
            "street": self.address or False,
            "city": self.city or False,
            "state_id": self.env.ref("base.state_ar_b").id,
            "country_id": self.env.ref("base.ar").id,
            "comment": note or False,
        })

    def _phantom_creation_chatter_message(self, trigger):
        """Body posted (via message_post, not message_notify -- this is a
        permanent chatter log entry on the document itself, not a
        transient notification) on the account.move/account.payment that
        this record's own _phantom_create_document just created, so
        anyone opening it in Odoo can see at a glance it came from the
        Phantom integration and whether this particular run was the
        automatic cron or a manual 'Process now'.
        """
        self.ensure_one()
        return (
            _("Created by the Phantom integration (automatic process).")
            if trigger == "automatic"
            else _("Created by the Phantom integration (manual process).")
        )
