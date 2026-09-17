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
