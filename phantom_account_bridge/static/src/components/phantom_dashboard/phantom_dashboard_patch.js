import { PhantomDashboard } from "@phantom_connector/components/phantom_dashboard/phantom_dashboard";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

patch(PhantomDashboard.prototype, {
    setup() {
        super.setup();
        this.labels.processNow = _t("Process now");
        this.state.processing = false;
    },

    async onProcessNowClick() {
        this.state.processing = true;
        try {
            await this.orm.call("res.company", "action_phantom_create", [[user.activeCompany.id]]);
            this.notification.add(_t("Phantom document creation finished"), { type: "success" });
            await this.fetchData();
        } finally {
            this.state.processing = false;
        }
    },
});
