import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Layout } from "@web/search/layout";
import { formatMonetary, formatDateTime } from "@web/views/fields/formatters";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { DashboardsKpiCard } from "@dashboards_base/components/kpi_card/kpi_card";
import { Component, onWillStart, useState } from "@odoo/owl";

export class PhantomDashboard extends Component {
    static template = "phantom_connector.PhantomDashboard";
    static components = { Layout, DashboardsKpiCard };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.labels = {
            invoicesThisMonth: _t("Invoices this month"),
            invoicesLastMonth: _t("Invoices last month"),
            receiptsThisMonth: _t("Receipts this month"),
            receiptsLastMonth: _t("Receipts last month"),
            pendingInvoices: _t("Pending invoices"),
            pendingReceipts: _t("Pending receipts"),
            errorInvoices: _t("Invoices with errors"),
            errorReceipts: _t("Receipts with errors"),
            lastRead: _t("Last successful Phantom read"),
            lastCreation: _t("Last document creation from Phantom"),
            importNow: _t("Import now"),
        };
        this.never = _t("Never");
        this.state = useState({ data: null, importing: false });

        onWillStart(async () => {
            await this.fetchData();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    formatMonetary(value) {
        return formatMonetary(value || 0, { currencyId: this.state.data.currency_id });
    }

    formatDateTime(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : this.never;
    }

    async fetchData() {
        this.state.data = await this.orm.call("phantom.dashboard", "get_dashboard_data", []);
    }

    async onDrilldownClick(drilldown) {
        if (drilldown) {
            await this.action.doAction(drilldown);
        }
    }

    async onImportNowClick() {
        this.state.importing = true;
        try {
            await this.orm.call("res.company", "action_phantom_import", [[user.activeCompany.id]]);
            this.notification.add(_t("Phantom import finished"), { type: "success" });
            await this.fetchData();
        } finally {
            this.state.importing = false;
        }
    }
}

registry.category("actions").add("phantom_connector.dashboard", PhantomDashboard);
