import re

from stdnum.ar import cuit as ar_cuit, dni as ar_dni

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

# CUIT and CUIL are numerically identical (stdnum.ar.cuit validates both --
# same 11-digit length, same prefix table, same check-digit algorithm; only
# the prefix's real-world meaning differs). AFIP convention: prefixes 20/23/
# 24/27 are issued to individuals (CUIL), 30/33/34/50/51/55 to companies/
# international entities (CUIT). Used only to *label* an already-valid
# 11-digit number correctly, confirmed with the user 2026-09-25.
_CUIL_PREFIXES = {"20", "23", "24", "27"}


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

    def _phantom_identification_is_valid(self, identification_type, digits):
        """Same format check Odoo itself runs before saving (see l10n_ar's
        res.partner._l10n_ar_identification_validation, backed by the
        stdnum.ar library) -- reused here as a pre-check so we only correct
        a document number when it would actually fail, never touch an
        already-valid one.
        """
        afip_code = identification_type.l10n_ar_afip_code
        if afip_code == "96":
            return ar_dni.is_valid(digits)
        if afip_code in ("80", "86"):
            return ar_cuit.is_valid(digits)
        return True

    def _phantom_sanitize_identification(self, identification_type, vat):
        """Correct a Phantom-supplied document number that would otherwise
        fail Odoo's DNI/CUIT/CUIL format validation and block the whole
        invoice/receipt from ever being created, instead of raising --
        these documents were already fiscalized by Phantom, the data
        quality issue is only in how the raw document number was
        transcribed. A well-formed value is returned unchanged.

        User-confirmed correction rules (2026-09-25), applied by digit
        count of the document with all non-digit characters stripped:
        - 7 or 8 digits: already a valid DNI, nothing to do.
        - Fewer than 7 digits: right-pad with zeros to 8 (DNI's valid
          length) -- e.g. "11111" -> "11111000". (Not 10: Odoo/AFIP only
          accept 7 or 8 digits for DNI, see stdnum.ar.dni.)
        - Exactly 11 digits: if it passes CUIT/CUIL's checksum+prefix
          check, re-tag as CUIT or CUIL by prefix (see _CUIL_PREFIXES). If
          it fails checksum/prefix, there is no way to "fix" a bad check
          digit without fabricating data -- fall back to DNI with a blank
          value (Odoo's own identification validation only runs on a
          non-empty vat, so a blank one never raises).
        - Anything else (9-10 digits, or no digits at all after a
          non-numeric value): can't be a valid DNI (too long) or CUIT/CUIL
          (wrong length) -- tag as "ID Extranjera"
          (l10n_latam_base.it_fid), which has no format validation in
          l10n_ar at all -- unless there are no digits whatsoever, in
          which case use a fixed placeholder DNI instead of leaving the
          document blank.
        """
        self.ensure_one()
        if not identification_type:
            return identification_type, vat

        digits = re.sub(r"\D", "", vat or "")
        if self._phantom_identification_is_valid(identification_type, digits):
            return identification_type, vat

        dni_type = self.env.ref("l10n_ar.it_dni")
        if not digits:
            return dni_type, "22222222"
        if len(digits) < 7:
            return dni_type, digits.ljust(8, "0")
        if len(digits) == 11:
            if ar_cuit.is_valid(digits):
                cuil_or_cuit = "l10n_ar.it_CUIL" if digits[:2] in _CUIL_PREFIXES else "l10n_ar.it_cuit"
                return self.env.ref(cuil_or_cuit), digits
            return dni_type, False
        return self.env.ref("l10n_latam_base.it_fid"), digits

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
        identification_type, vat = self._phantom_sanitize_identification(identification_type, vat)
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
