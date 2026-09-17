Turns pending ``phantom.invoice``/``phantom.receipt`` staging records
(imported by ``phantom_connector``) into real Argentine ``account.move``
invoices and ``account.payment`` receipts, matching customers by
identification (CUIT/DNI + document number, not a Phantom-specific field),
and reconciling a receipt against its associated invoice when Phantom
reports that link.

Every invoice created this way carries a configurable
``account.move.classification`` tag, making the whole batch easy to filter
and report on.
