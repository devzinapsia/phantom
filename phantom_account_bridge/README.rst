========================
Phantom Account Bridge
========================

Turns pending ``phantom.invoice``/``phantom.receipt`` staging records
(imported by ``phantom_connector``) into real Argentine ``account.move``
invoices and ``account.payment`` receipts, matching customers by
identification (CUIT/DNI + document number, not a Phantom-specific field),
and reconciling a receipt against its associated invoice when Phantom
reports that link.

Every invoice created this way carries a configurable
``account.move.classification`` tag, making the whole batch easy to filter
and report on.

**Table of contents**

.. contents::
   :local:

Configuration
=============

Go to **Phantom ‣ Configuration** (the same dedicated screen added by
``phantom_connector``, visible to **Administrator** users only), in the
**Documents** section (only shown once **Enable Phantom integration** is
checked):

* **Sales journal**: the journal used for every invoice/credit note/debit
  note created from Phantom. Must be configured for AFIP documents
  (``l10n_latam_use_documents``), like any other Argentine sales journal.
* **Receipt journal**: the bank/cash journal used for every payment
  created from Phantom.
* **Default product**: the only product used on invoice lines -- Phantom
  does not report products mappable to Odoo, only free text in
  "Detalle".
* **Analytic account**: applied at 100% to every invoice line created by
  this integration. Optional.
* **Classification**: applied to every invoice created by this
  integration (from ``account_move_classification``), so they can be
  filtered/reported on separately from manually-entered invoices.
* **Creation time**: only shown in Automatic mode. Local time of day, in
  the "Import timezone" from ``phantom_connector``, at which the
  automatic document-creation cron runs, once per day.

Usage
=====

Once configured, this module processes every ``pending`` Phantom invoice/
receipt of the current company -- manually via **Phantom ‣ Import now**
(processes both staging import and document creation), or automatically
once a day if the company's processing mode is Automatic, using the same
"Creation time" mechanism as the import cron.

Customer matching
------------------

Customers are matched by identification, never by Phantom's own "IDA":
``res.partner`` is never extended with a Phantom-specific field. Phantom's
"Doc_Tipo" (an AFIP identification-type code) is mapped to
``l10n_latam.identification.type`` via its ``l10n_ar_afip_code``, and
"Documento" is matched against ``res.partner.vat``. If a partner with that
identification type and number already exists, it is reused as-is --
existing data is never overwritten, so manual edits in Odoo are safe. If
none exists, a new one is created from "RS" (name), "Dirección" (street)
and "Ciudad" (city).

Invoice creation
------------------

Phantom's "Tipo" (Factura/NC/ND) maps to Odoo as follows:

======== ================= ==========================================
Tipo     move_type         l10n_latam.document.type.internal_type
======== ================= ==========================================
Factura  out_invoice       invoice
ND       out_invoice       debit_note
NC       out_refund        credit_note
======== ================= ==========================================

"ND" (debit note) has no dedicated ``move_type`` in Odoo/Argentina: like
"Factura", it is an ``out_invoice``, distinguished only by its document
type. The specific document type is found by combining the mapped
``internal_type`` above with Phantom's "Tipo_Comp" letter (A/B/C) via
``l10n_ar_letter``.

"Detalle" is parsed into one invoice line per item (format ``ID_ART,
DESCRIPCIÓN, NETO, %IMP, TOTAL;``, repeated, separated by ``;``), all
using the configured **Default product**. Each item's "%IMP" is matched
to an existing sale ``account.tax`` at that exact percentage in the
company; if none is found, the record is left in **Error** rather than
posting an invoice with the wrong (or no) VAT -- add the missing tax
rate to the company's chart of accounts and it will be picked up on the
next run. If "Detalle" can't be parsed into any item, a single fallback
line is created from the staging record's own totals.

Every invoice is posted immediately (not left in draft) and tagged with
the configured **Classification**.

Receipt creation
------------------

Each pending receipt becomes a posted ``account.payment``
(``payment_type = 'inbound'``, ``partner_type = 'customer'``) for
"Importe_Total", on the configured **Receipt journal**.

Imputation (reconciliation)
-----------------------------

If an invoice's "Comp_Asociado" (associated receipt number) is set:

* If that receipt has already been turned into a payment, they are
  reconciled immediately.
* If not yet (processing order, or the receipt arrives in a later
  Phantom run), the invoice is still created normally -- it is only
  flagged internally for a reconciliation retry, which is attempted
  again on every subsequent creation run until the receipt shows up.
  This is not an error.

If "Comp_Asociado" is empty, the invoice (and any receipt for that
customer) is simply left unreconciled -- a normal "on account" payment,
not a problem to flag.

Errors and traceability
-------------------------

A failure on one invoice or receipt (e.g. missing tax rate, unknown
document type/letter) never stops the rest of the batch: that record is
left in **Error** with the failure message, and everything else is
processed normally.

Every ``phantom.invoice``/``phantom.receipt`` that was successfully
processed shows a smart button to its real ``account.move``/
``account.payment``; the reverse is also true, so tracing "why does this
invoice exist" or "what did this Phantom voucher become" both work from
either side.

Bug Tracker
===========

Bugs are tracked on
`GitHub Issues <https://github.com/devzinapsia/phantom/issues>`_.
In case of trouble, please check there if your issue has already been
reported.

Credits
=======

Authors
-------

* Zinapsia

Maintainers
-----------

This module is maintained by Zinapsia.

This module is part of the
`phantom <https://github.com/devzinapsia/phantom>`_
project.
