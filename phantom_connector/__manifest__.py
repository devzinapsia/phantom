{
    "name": "Phantom Connector",
    "version": "19.0.1.0.7",
    "summary": "Import invoices and receipts from the Phantom billing/collections API into staging models",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Accounting/Accounting",
    "depends": ["mail", "dashboards_base"],
    "data": [
        "security/phantom_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "wizards/views/phantom_settings_wizard_views.xml",
        "views/phantom_invoice_views.xml",
        "views/phantom_receipt_views.xml",
        "views/phantom_dashboard_views.xml",
        "views/phantom_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "phantom_connector/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
