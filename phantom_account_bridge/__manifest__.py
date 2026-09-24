{
    "name": "Phantom Account Bridge",
    "version": "19.0.1.1.2",
    "summary": "Create real invoices, receipts and reconciliations from Phantom staging data",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Accounting/Accounting",
    "depends": ["phantom_connector", "account", "account_move_classification", "l10n_ar", "l10n_ar_edi"],
    "data": [
        "data/ir_cron_data.xml",
        "wizards/views/phantom_settings_wizard_views.xml",
        "views/phantom_invoice_views.xml",
        "views/phantom_receipt_views.xml",
        "views/account_move_views.xml",
        "views/account_payment_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "phantom_account_bridge/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
