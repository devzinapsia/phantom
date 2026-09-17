Access rights
=============

This module adds its own **Phantom** entry to **Settings ‣ Users &
Companies ‣ Users**, on the *Access Rights* tab:

* **User**: can view Phantom invoices/receipts and the dashboard, and
  trigger a manual import.
* **Administrator**: everything **User** can do, plus access to
  **Phantom ‣ Configuration**, where the API URL/credentials and
  schedule are set. This does **not** require the user to also be an
  Odoo Technical/System Administrator -- Phantom's own configuration
  screen is deliberately independent of the generic Settings page,
  which only System Administrators can open at all.

Configuration
=============

Go to **Phantom ‣ Configuration** (visible to **Administrator** users
only):

* **Enable Phantom integration**: master switch for this company. All
  other fields below only show once this is checked.
* **Phantom API URL**: the Phantom endpoint, e.g.
  ``http://IPPHANTOM/Includes/CRM/API_CRM.php``.
* **Phantom API user** / **Phantom API password**: credentials of a
  superuser-profile API account created in Phantom itself (**Phantom ‣
  Configuraciones ‣ Usuarios**).
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
