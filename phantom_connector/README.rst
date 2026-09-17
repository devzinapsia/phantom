=================
Phantom Connector
=================

Connects to Phantom's API CRM II, per company, and keeps a local staging
copy of every invoice, credit note, debit note and payment receipt it
reports -- without turning any of it into a real Odoo accounting document.

Each company can be configured with its own Phantom URL and credentials.
Imports can be triggered manually at any time, or scheduled to run once a
day, automatically, at a configured local time. Every run re-queries a
rolling window of recent days (not just "today"), so vouchers Phantom loads
or edits late are still picked up on a later run.

Re-importing a voucher Phantom already reported updates the staging record
in place; it never overwrites the status of one that has already been
turned into a real invoice/receipt by another module (e.g.
``phantom_account_bridge``, if installed) -- that transformation step, and
everything downstream of it, is out of scope for this module by design.

**Table of contents**

.. contents::
   :local:

Configuration
=============

Go to **Settings ‣ General Settings**, in the **Phantom integration**
section:

* **Enable Phantom integration**: master switch for this company. All
  other fields below only show once this is checked.
* **Phantom API URL**: the Phantom endpoint, e.g.
  ``http://IPPHANTOM/Includes/CRM/API_CRM.php``.
* **Phantom API user** / **Phantom API password**: credentials of a
  superuser-profile API account created in Phantom itself (**Phantom ‣
  Configuraciones ‣ Usuarios**). The password field is only visible to
  users in the **Technical Settings** group.
* **Processing mode**: **Manual** (the only way to import is the "Import
  now" button/action below) or **Automatic** (also runs once a day on
  its own, in addition to "Import now" still being available to force an
  out-of-schedule run).
* **Import timezone**: only shown in Automatic mode. Timezone used to
  evaluate **Import time** below. Suggested automatically from the
  company's country when every zone in that country currently shares the
  same UTC offset (e.g. Argentina); left empty otherwise -- it is never
  assumed from the server, so set it explicitly if it is not suggested.
* **Import time**: only shown in Automatic mode. Local time of day, in
  the timezone above, at which the automatic import runs, once per day.
  The cron that checks this runs every 15 minutes, so the actual run can
  be up to that long after the configured time.
* **Sweep window (days)**: how many days back are re-queried on every
  run (using Phantom's transaction date, not the voucher date, so
  vouchers loaded into Phantom late are not missed). Default: 7.

Field mapping (Phantom API field → staging field) is documented in
``models/phantom_invoice.py`` and ``models/phantom_receipt.py``, next to
each field.

Usage
=====

Importing
---------

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
---------

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
