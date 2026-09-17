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
