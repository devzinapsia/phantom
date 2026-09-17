Importing
=========

* **Manual mode**: use **Phantom ‣ Import now** (or the button in
  Settings) whenever you want to pull the latest invoices/receipts for
  the current company.
* **Automatic mode**: once a day, at the configured local time, the
  system authenticates against Phantom and queries both
  ``Consultar_Transacciones_Facturacion`` and
  ``Consultar_Transacciones_Pagos`` for the configured sweep window,
  filtered by transaction date (not voucher date) so late-loaded
  vouchers are not missed. "Import now" still works in this mode, to
  force a run outside the schedule.

Every voucher Phantom reports is matched by its ``IDT`` (Phantom
transaction ID) within the current company:

* If it doesn't exist yet, a new ``phantom.invoice``/``phantom.receipt``
  is created with status **Pending**.
* If it already exists, its fields are refreshed with the latest data
  from Phantom -- except its status, which an import never changes. In
  particular, a voucher already **Processed** (turned into a real
  ``account.move``/``account.payment`` by another module, e.g.
  ``phantom_account_bridge``) is never reopened by a later import.

A failure on one voucher, or on one company (in automatic mode, across
several companies), never stops the rest of the batch: it is logged and
skipped. An automatic-mode failure also notifies **Technical Settings**
users so it doesn't go unnoticed.

Reviewing
=========

**Phantom ‣ Invoices** and **Phantom ‣ Receipts** list every staged
voucher for the current company, with filters for status (Pending/
Processed/Error), company, and voucher date range, and "Group By" options
for status and company. Both are read-only: they reflect what Phantom
reported, not something to edit by hand.

**Phantom ‣ Dashboard** shows, for the current company: invoices
imported this month and last month (count and amount), invoices and
receipts currently pending, and the date/time of the last successful
Phantom read. It also shows the last time documents were created from
Phantom in Odoo -- that indicator is defined here so the dashboard works
even without ``phantom_account_bridge`` installed (it shows blank/"Never"
in that case), but is only ever set by that module.
